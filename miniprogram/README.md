# 影像知情微信小程序

这是面向患者的微信小程序客户端骨架。它复用当前项目的 `/api/reports/ocr` 接口，但不会直接连接本机服务。

## 在微信开发者工具中打开

1. 导入 `miniprogram` 目录。
2. 填写你的 AppID（开发工具内或 `project.config.json`）。
3. 将 `config.js` 的 `apiBaseUrl` 改成生产 HTTPS API 域名。
4. 在微信公众平台的“开发管理 > 开发设置”配置该域名为 request 与 uploadFile 合法域名。
5. 在小程序后台按实际功能配置隐私保护指引，并将隐私政策链接填入 `config.js`。

## 后端要求

生产 API 必须：

- 使用 HTTPS、用户认证和短期上传凭证；
- 支持 `POST /api/reports/ocr`，接收 multipart 字段 `file`；
- 返回 `source_status`、`full_text`、`lines`；
- 不在客户端或日志中保存病历内容；
- 对图片 OCR 的低置信度结果要求用户核对。

当前本地 FastAPI 是开发原型，**不能**直接发布给小程序使用。

