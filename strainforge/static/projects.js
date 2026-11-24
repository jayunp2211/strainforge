/* Project picker in the Save box (main calculator and tool pages).
   Reads BOOT.projects from the page; calc.js and builtin.js call SFProject.body() when saving
   and SFProject.adopt(savedRow) afterwards. */
(function () {
  const boot = JSON.parse(document.getElementById('boot').textContent).projects;
  const sel = document.getElementById('calcProject'), input = document.getElementById('newProject');
  if (!boot || !sel) { window.SFProject = { body: () => ({}), adopt() {}, onChange() {} }; return; }
  const NEW = '__new__';
  const KEY = 'sf-project-' + boot.ws;
  const listeners = [];
  let list = boot.list.slice();

  function draw(selected) {
    sel.innerHTML = '';
    sel.add(new Option('No project', ''));
    list.slice().sort((a, b) => a.name.localeCompare(b.name)).forEach(p => sel.add(new Option(p.name, p.id)));
    sel.add(new Option('+ New project…', NEW));
    sel.value = list.some(p => p.id === selected) ? selected : '';
  }
  function remembered() { try { return localStorage.getItem(KEY) || ''; } catch (e) { return ''; } }
  function remember(id) { try { id ? localStorage.setItem(KEY, id) : localStorage.removeItem(KEY); } catch (e) { /* private window */ } }
  function syncInput() {
    input.hidden = sel.value !== NEW;
    if (!input.hidden) input.focus();
  }

  // An opened result shows its own project; a fresh one uses ?project= or the last project you saved into.
  const saved = JSON.parse(document.getElementById('boot').textContent).saved;
  draw(saved ? (boot.current || '') : (boot.preset || remembered()));

  sel.addEventListener('change', () => { syncInput(); listeners.forEach(f => f()); });
  input.addEventListener('input', () => listeners.forEach(f => f()));

  window.SFProject = {
    /** Fields to merge into the save request. */
    body() {
      if (sel.value === NEW) {
        const name = input.value.trim();
        if (!name) { input.focus(); input.placeholder = 'Name the new project first'; throw new Error('Name the new project first'); }
        return { new_project: name };
      }
      return { project_id: sel.value || null };
    },
    /** After a save: pick up a project that was just created and remember the choice. */
    adopt(row) {
      if (!row) return;
      const id = row.project_id ? String(row.project_id) : '';
      if (id && !list.some(p => p.id === id)) list.push({ id, name: row.project_name, n: 1 });
      draw(id);
      input.value = ''; input.hidden = true;
      remember(id);
    },
    /** Called when the person changes the project (the page marks the result unsaved). */
    onChange(f) { listeners.push(f); },
  };
})();
