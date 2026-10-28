const form = document.querySelector('#composer-form');
const textarea = document.querySelector('#notes');
const feedback = document.querySelector('#feedback');
const fileList = document.querySelector('#file-list');
const generateButton = document.querySelector('#generate-button');
const notePattern = /^[A-G](?:[0-8])?$/;

function readNotes() {
  const raw = textarea.value.trim();
  const expression = raw.match(/^\(:\)\s*\{([\s\S]*)\}\s*$/);
  if (raw.includes('(:)') || raw.includes('{') || raw.includes('}')) {
    if (!expression) throw new Error('Formato esperado: (:) {C4 D4 E4}.');
    return expression[1].replaceAll(',', ' ').trim().split(/\s+/).filter(Boolean);
  }
  return raw.replaceAll(',', ' ').split(/\s+/).filter(Boolean);
}

function showFeedback(message, isError = false) {
  feedback.hidden = false;
  feedback.classList.toggle('error', isError);
  feedback.textContent = message;
}

async function makeDownload(file) {
  const response = await fetch(file.url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`No se pudo descargar ${file.name}.`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== file.size) {
    throw new Error(`${file.name} llegó incompleto (${bytes.byteLength} de ${file.size} bytes).`);
  }
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const actualHash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  if (actualHash !== file.sha256) throw new Error(`${file.name} no pasó la verificación de integridad.`);
  if (file.name.endsWith('.ly')) {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    if (!text.endsWith('}\n') || !text.includes('\\score {')) {
      throw new Error(`${file.name} llegó incompleto o no es una partitura legible.`);
    }
  }
  const blob = new Blob([bytes], { type: response.headers.get('Content-Type') || 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.className = 'file-link';
  link.href = url;
  link.download = file.name;
  const extension = file.name.split('.').pop().toUpperCase();
  const type = document.createElement('span');
  type.className = 'file-extension';
  type.textContent = extension;
  const name = document.createElement('span');
  name.className = 'file-name';
  name.textContent = file.name;
  link.append(type, name);
  return link;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  let notes;
  fileList.replaceChildren();
  feedback.textContent = '';
  try {
    notes = readNotes();
  } catch (error) {
    showFeedback(error.message, true);
    return;
  }
  if (!notes.length) return showFeedback('Escribe una secuencia de notas antes de generar.', true);
  if (notes.length > 512) {
    return showFeedback('El máximo permitido es de 512 notas por generación.', true);
  }
  const invalid = notes.filter((note) => !notePattern.test(note));
  if (invalid.length) {
    return showFeedback(`Revisa estas notas: ${invalid.slice(0, 6).join(', ')}. Usa A-G y una octava opcional, por ejemplo C4.`, true);
  }

  generateButton.disabled = true;
  generateButton.querySelector('.button-label').textContent = 'Generando…';
  showFeedback('Preparando la partitura y convirtiendo los archivos…');
  try {
    const response = await fetch('/api/generar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: textarea.value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'No se pudieron generar los archivos.');
    for (const file of payload.files) {
      fileList.append(await makeDownload(file));
    }
    showFeedback(`Archivos generados para ${payload.notes.length} notas.`);
  } catch (error) {
    showFeedback(error.message || 'No fue posible conectar con el servidor local.', true);
  } finally {
    generateButton.disabled = false;
    generateButton.querySelector('.button-label').textContent = 'Generar archivos';
  }
});
