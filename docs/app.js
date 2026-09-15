const fileInput = document.querySelector('#file');
const button = document.querySelector('#convert');
const statusEl = document.querySelector('#status');
const label = document.querySelector('#fileLabel');
const drop = document.querySelector('#drop');
let pyodide;
let templateBytes;

function status(message, kind = '') {
  statusEl.textContent = message;
  statusEl.className = kind;
}

async function initialize() {
  try {
    pyodide = await loadPyodide();
    const [source, template] = await Promise.all([
      fetch('ykw_3ds_to_switch.py').then(r => { if (!r.ok) throw new Error('converter source missing'); return r.text(); }),
      fetch('assets/switch_fresh_template.yw').then(r => { if (!r.ok) throw new Error('template missing'); return r.arrayBuffer(); })
    ]);
    pyodide.FS.writeFile('/home/pyodide/ykw_3ds_to_switch.py', source);
    templateBytes = new Uint8Array(template);
    await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/home/pyodide'); import ykw_3ds_to_switch");
    button.disabled = !fileInput.files.length;
    button.textContent = 'Convert to Switch save';
    status('Ready. Nothing is uploaded.');
  } catch (error) {
    status(`Could not initialize: ${error.message}`, 'error');
    button.textContent = 'Initialization failed';
  }
}

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  label.textContent = file ? `${file.name} • ${file.size.toLocaleString()} bytes` : 'Choose a 3DS save';
  button.disabled = !pyodide || !file;
});

for (const event of ['dragenter', 'dragover']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.add('drag'); });
for (const event of ['dragleave', 'drop']) drop.addEventListener(event, e => { e.preventDefault(); drop.classList.remove('drag'); });
drop.addEventListener('drop', event => {
  if (event.dataTransfer.files.length) {
    fileInput.files = event.dataTransfer.files;
    fileInput.dispatchEvent(new Event('change'));
  }
});

button.addEventListener('click', async () => {
  const file = fileInput.files[0];
  if (!file) return;
  button.disabled = true;
  status('Converting and validating…');
  try {
    const input = new Uint8Array(await file.arrayBuffer());
    pyodide.globals.set('browser_input', input);
    pyodide.globals.set('browser_template', templateBytes);
    await pyodide.runPythonAsync("browser_output = ykw_3ds_to_switch.convert(bytes(browser_input), bytes(browser_template))");
    const proxy = pyodide.globals.get('browser_output');
    const output = proxy.toJs();
    proxy.destroy();
    const blob = new Blob([output], {type:'application/octet-stream'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${file.name.replace(/\.yw$/i, '')}-switch.yw`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status(`Converted successfully • ${output.length.toLocaleString()} bytes`, 'ok');
  } catch (error) {
    status(`Conversion failed: ${error.message}`, 'error');
  } finally {
    button.disabled = false;
  }
});

initialize();
