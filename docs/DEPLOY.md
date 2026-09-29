# 生产部署指南（Alibaba Cloud Linux 3 实测）

以下步骤在一台 **2 vCPU / 2 GiB** 的阿里云 ECS（Alibaba Cloud Linux 3）上完整验证过。
其他 systemd 发行版（Ubuntu / Debian / CentOS）步骤类似，包管理器换成 `apt`/`yum` 即可。

## 1. 准备环境

```bash
# Python 3.11+（系统自带即可，或自行安装）
python3 --version

# 拉取代码
git clone <your-repo-url> ~/imaging-informed
cd ~/imaging-informed

# 虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip -i https://mirrors.aliyun.com/pypi/simple/
```

## 2. 小内存机器必做：加 swap

2 GiB 内存加载 PaddleOCR 模型时容易被 OOM Kill，先加 2G swap：

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. 安装依赖

```bash
# opencv 运行时需要的系统库
sudo dnf install -y mesa-libGL libgomp

pip install -r backend/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## 4. 预热 OCR 模型

首次运行会下载 PP-OCRv5 mobile 模型（数百 MB），先手动跑一次确认成功：

```bash
cd ~/imaging-informed
python -c "
from backend.ocr import _get_engine
_get_engine()
print('engine ok')
"
```

> **已知坑：PaddlePaddle 3.x + OneDNN**
> 部分 CPU 型号上，Paddle 3.x 默认开启的 OneDNN 加速会在推理时崩溃：
> `NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support`。
> 本项目代码已通过 `enable_mkldnn=False` 强制关闭 OneDNN（见 `backend/ocr.py`），
> 推理走纯 CPU 算子。如果升级 paddle 版本后出现上述报错，先检查这个参数是否还在。

## 5. 配置 LLM（可选，不配则解读接口返回 503）

```bash
sudo cp deploy/imaging-ocr.env.example /etc/imaging-ocr.env
sudo chmod 600 /etc/imaging-ocr.env
sudo vi /etc/imaging-ocr.env   # 填入真实 API Key
```

## 6. systemd 常驻（开机自启 + 崩溃自动拉起）

```bash
# 按实际情况修改 Unit 文件里的 User 与路径，然后安装
sudo cp deploy/imaging-ocr.service /etc/systemd/system/imaging-ocr.service
sudo systemctl daemon-reload
sudo systemctl enable --now imaging-ocr
sudo systemctl status imaging-ocr --no-pager
```

注意事项：

- `WorkingDirectory` 必须是仓库根目录，且以 `backend.main:app` 形式启动
  （`backend/main.py` 使用相对导入，进到 `backend/` 目录里跑 `uvicorn main:app` 会 ImportError）
- `ExecStart` 中的 python 用虚拟环境里的绝对路径
- 日志：`journalctl -u imaging-ocr -f`

## 7. 防火墙与安全组

- 云厂商**安全组**放行 TCP 8000（或你在 Nginx 反代后只用 443）
- 系统防火墙（如启用 firewalld）：`sudo firewall-cmd --add-port=8000/tcp --permanent && sudo firewall-cmd --reload`

## 8. 验证

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","service":"report-ocr"}

curl -F "file=@backend/fixtures/sample-report.txt" http://127.0.0.1:8000/api/reports/ocr
```

## 9. 生产化后续（强烈建议）

对外提供服务前，至少完成：

1. **HTTPS**：注册域名 → ICP 备案 → Nginx 反代到 127.0.0.1:8000 → Let's Encrypt 证书。
   微信小程序正式版只允许 HTTPS + 已备案域名。
2. **访问控制**：当前接口无认证，公网裸奔任何人都能调用（会产生 LLM 费用）。
3. **限流**：按 IP 限制 OCR/interpret 调用频率。
