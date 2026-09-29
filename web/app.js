const reportInput = document.querySelector('#report-file');
const reportFileName = document.querySelector('#report-file-name');
const analyzeButton = document.querySelector('#analyze-button');
const demoButton = document.querySelector('#demo-button');
const processing = document.querySelector('#processing');
const results = document.querySelector('#results');
const restartButton = document.querySelector('#restart-button');

function showResults() {
  processing.classList.add('hidden');
  results.classList.remove('hidden');
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function analyzeReport() {
  const [file] = reportInput.files;
  if (!file) return;
  processing.classList.remove('hidden');
  analyzeButton.disabled = true;

  try {
    const data = new FormData();
    data.append('file', file);
    const response = await fetch('http://127.0.0.1:8000/api/reports/ocr', { method: 'POST', body: data });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || '无法读取这份报告');
    }
    const result = await response.json();
    document.querySelector('.raw-text pre').textContent = result.full_text || '没有识别到可用文字，请上传更清晰的报告照片。';
    document.querySelector('.demo-badge').textContent = result.source_status === 'needs_review' ? '请核对文字' : '已完成 OCR';
    showResults();
  } catch (error) {
    processing.classList.add('hidden');
    window.alert(`报告尚未完成读取：${error.message}。请确认后端已启动，或使用“查看匿名演示结果”。`);
  } finally {
    analyzeButton.disabled = false;
  }
}

reportInput.addEventListener('change', () => {
  const [file] = reportInput.files;
  reportFileName.textContent = file ? file.name : '尚未选择文件';
  analyzeButton.disabled = !file;
});

analyzeButton.addEventListener('click', () => {
  analyzeReport();
});

demoButton.addEventListener('click', showResults);
restartButton.addEventListener('click', () => {
  results.classList.add('hidden');
  reportInput.value = '';
  reportFileName.textContent = '尚未选择文件';
  analyzeButton.disabled = true;
  document.querySelector('.hero').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

