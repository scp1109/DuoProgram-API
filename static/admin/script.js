// API_BASE se detecta automaticamente segun donde este corriendo el servidor.
// En local apunta a localhost:8000; en Railway usa el mismo host del dashboard.
const API_BASE = window.location.port === '8000'
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : `${window.location.protocol}//${window.location.hostname}`;

let currentPage = 'dashboard';
let currentProgramaId = null;

// -- Menu lateral (responsive) --------------------------------

function abrirMenu() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('overlay').classList.add('visible');
}

function cerrarMenu() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('overlay').classList.remove('visible');
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentPage = btn.dataset.page;
            document.getElementById('page-title').textContent = btn.textContent.trim();
            cerrarMenu(); // cerrar menu en movil al navegar
            loadPage(currentPage);
        });
    });
    loadPage('dashboard');
});

async function loadPage(page) {
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Cargando...</div>';
    switch(page) {
        case 'dashboard': await loadDashboard(); break;
        case 'programas': await loadProgramas(); break;
        case 'materias':  await loadMaterias();  break;
        case 'usuarios':  await loadUsuarios();  break;
        case 'planes':    await loadPlanes();    break;
    }
}

// -- Dashboard ------------------------------------------------

async function loadDashboard() {
    try {
        const res = await fetch(`${API_BASE}/admin/stats`);
        const stats = await res.json();
        document.getElementById('content').innerHTML = `
            <div class="stats-grid">
                <div class="stat-card"><h3>${stats.total_usuarios || 0}</h3><p>Usuarios registrados</p></div>
                <div class="stat-card"><h3>${stats.total_planes || 0}</h3><p>Planes generados</p></div>
                <div class="stat-card"><h3>${stats.total_programas || 0}</h3><p>Programas</p></div>
                <div class="stat-card"><h3>${stats.total_materias || 0}</h3><p>Materias</p></div>
            </div>`;
    } catch(e) {
        document.getElementById('content').innerHTML = '<p>Error cargando dashboard</p>';
        console.error(e);
    }
}

// -- Usuarios -------------------------------------------------

async function loadUsuarios() {
    try {
        const res = await fetch(`${API_BASE}/admin/usuarios`);
        const data = await res.json();
        let html = `<div class="table-container"><table>
            <thead><tr><th>ID</th><th>Nombre</th><th>Email</th><th>Fecha Registro</th></tr></thead>
            <tbody>`;
        if (data.usuarios && data.usuarios.length > 0) {
            for (const u of data.usuarios) {
                html += `<tr>
                    <td>${u.id}</td>
                    <td>${u.nombre_completo}</td>
                    <td>${u.email}</td>
                    <td>${new Date(u.created_at).toLocaleDateString()}</td>
                </tr>`;
            }
        } else {
            html += '<tr><td colspan="4" style="text-align:center;padding:40px;">No hay usuarios</td></tr>';
        }
        html += '</tbody></table></div>';
        document.getElementById('content').innerHTML = html;
    } catch(e) {
        document.getElementById('content').innerHTML = '<p>Error cargando usuarios</p>';
        console.error(e);
    }
}

// -- Planes ---------------------------------------------------

async function loadPlanes() {
    try {
        const res = await fetch(`${API_BASE}/admin/planes`);
        const data = await res.json();
        let html = `<div class="table-container"><table>
            <thead><tr><th>ID</th><th>Usuario</th><th>Principal</th><th>Secundario</th><th>Semestres</th><th>Promedio</th><th>Fecha</th><th>Acciones</th></tr></thead>
            <tbody>`;
        if (data.planes && data.planes.length > 0) {
            for (const p of data.planes) {
                html += `<tr>
                    <td>${p.id}</td>
                    <td>${p.usuario}</td>
                    <td>${p.programa_principal}</td>
                    <td>${p.programa_secundario || '-'}</td>
                    <td>${p.semestres_cursados}</td>
                    <td>${p.promedio}</td>
                    <td>${new Date(p.created_at).toLocaleDateString()}</td>
                    <td><button class="btn-edit" onclick="verPlan(${p.id})">Ver</button></td>
                </tr>`;
            }
        } else {
            html += '<tr><td colspan="8" style="text-align:center;padding:40px;">No hay planes</td></tr>';
        }
        html += '</tbody></table></div>';
        document.getElementById('content').innerHTML = html;
    } catch(e) {
        document.getElementById('content').innerHTML = '<p>Error cargando planes</p>';
        console.error(e);
    }
}

async function verPlan(planId) {
    try {
        const res = await fetch(`${API_BASE}/admin/planes/${planId}`);
        const plan = await res.json();

        const secundario = plan.programa_secundario
            ? `${plan.nombre_secundario} (Secundario)`
            : 'Sin programa secundario';

        const encabezado = `Plan #${plan.id} — ${plan.usuario}<br>
            <span style="font-size:13px;font-weight:normal;color:#555;">
                ${plan.nombre_principal} (Principal) + ${secundario}
                &nbsp;|&nbsp; ${plan.semestres_cursados} semestres cursados
                &nbsp;|&nbsp; Promedio ${plan.promedio}
            </span>`;

        // Construir semestres
        const semestres = plan.plan_generado?.semestres || [];
        let semGrid = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin-top:16px;">';

        for (const sem of semestres) {
            semGrid += `
                <div style="background:#f8f9fa;border-radius:12px;padding:14px;border:1px solid #e0e0e0;">
                    <div style="font-weight:bold;color:#1A1FC8;margin-bottom:8px;font-size:13px;">
                        Semestre ${sem.numero} &nbsp;
                        <span style="font-weight:normal;color:#888;">${sem.total_creditos} cr</span>
                    </div>`;
            for (const mat of (sem.materias || [])) {
                const badge = mat.origen === 'compartida'
                    ? '#9C27B0' : mat.origen === 'secundario'
                    ? '#FF9800' : '#1A1FC8';
                semGrid += `
                    <div style="display:flex;justify-content:space-between;align-items:center;
                                padding:5px 0;border-bottom:1px solid #eee;font-size:12px;">
                        <span>${mat.nombre}</span>
                        <span style="background:${badge};color:white;padding:1px 7px;
                                     border-radius:10px;font-size:10px;margin-left:6px;white-space:nowrap;">
                            ${mat.creditos}cr
                        </span>
                    </div>`;
            }
            semGrid += '</div>';
        }
        semGrid += '</div>';

        // Modal
        const wrapper = document.createElement('div');
        wrapper.id = 'wrapperPlanModal';
        wrapper.innerHTML = `
            <div style="display:flex;position:fixed;top:0;left:0;width:100%;height:100%;
                        background:rgba(0,0,0,0.5);justify-content:center;align-items:center;z-index:1000;padding:16px;">
                <div style="background:white;padding:24px;border-radius:16px;width:100%;
                            max-width:900px;max-height:90vh;overflow-y:auto;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
                        <h2 style="color:#1A1FC8;font-size:17px;line-height:1.4;">${encabezado}</h2>
                        <button onclick="document.getElementById('wrapperPlanModal').remove()"
                            style="background:none;border:none;font-size:22px;cursor:pointer;
                                   color:#888;margin-left:12px;flex-shrink:0;">✕</button>
                    </div>
                    <div style="font-size:11px;color:#aaa;margin-bottom:4px;">
                        <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
                                     background:#1A1FC8;margin-right:4px;"></span>Principal
                        <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
                                     background:#FF9800;margin:0 4px 0 12px;"></span>Secundario
                        <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
                                     background:#9C27B0;margin:0 4px 0 12px;"></span>Compartida
                    </div>
                    ${semGrid}
                </div>
            </div>`;
        document.body.appendChild(wrapper);

    } catch(e) {
        alert('Error cargando el plan');
        console.error(e);
    }
}

// -- Programas ------------------------------------------------

async function loadProgramas() {
    try {
        const res = await fetch(`${API_BASE}/admin/programas`);
        const data = await res.json();
        let html = `
            <button class="btn-primary" onclick="showProgramaModal()">+ Nuevo Programa</button>
            <div class="table-container"><table>
                <thead><tr><th>Codigo</th><th>Nombre</th><th style="text-align:center;">Semestres</th><th>Facultad</th><th>Acciones</th></tr></thead>
                <tbody>`;
        if (data.programas && data.programas.length > 0) {
            for (const p of data.programas) {
                html += `<tr>
                    <td><strong>${p.codigo}</strong></td>
                    <td>${p.nombre}</td>
                    <td style="text-align:center;">${p.total_semestres}</td>
                    <td>${p.facultad}</td>
                    <td><button class="btn-danger" onclick="deletePrograma('${p.codigo}')">Eliminar</button></td>
                </tr>`;
            }
        } else {
            html += '<tr><td colspan="5" style="text-align:center;padding:40px;">No hay programas</td></tr>';
        }
        html += '</tbody></table></div>';
        document.getElementById('content').innerHTML = html;
    } catch(e) {
        document.getElementById('content').innerHTML = '<p>Error cargando programas</p>';
        console.error(e);
    }
}

async function deletePrograma(codigo) {
    if (!confirm(`¿Eliminar el programa ${codigo}?`)) return;
    try {
        const res = await fetch(`${API_BASE}/admin/programas/${codigo}`, { method: 'DELETE' });
        if (res.ok) { alert('Programa eliminado'); loadPage('programas'); }
        else alert('Error eliminando programa');
    } catch(e) { alert('Error eliminando programa'); }
}

function showProgramaModal() {
    const codigo   = prompt('Codigo del programa (ej: IMEC):');   if (!codigo)   return;
    const nombre   = prompt('Nombre completo del programa:');      if (!nombre)   return;
    const facultad = prompt('Facultad:');                          if (!facultad) return;

    fetch(`${API_BASE}/admin/programas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            codigo: codigo.toUpperCase(),
            nombre, facultad
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.id) { alert('Programa creado'); loadPage('programas'); }
        else alert('Error: ' + JSON.stringify(data));
    })
    .catch(() => alert('Error al crear el programa'));
}

// -- Materias -------------------------------------------------

async function loadMaterias() {
    try {
        const res = await fetch(`${API_BASE}/admin/programas`);
        const data = await res.json();

        let options = '<option value="">-- Seleccione un programa --</option>';
        if (data.programas) {
            for (const p of data.programas) {
                options += `<option value="${p.codigo}">${p.codigo} - ${p.nombre}</option>`;
            }
        }

        document.getElementById('content').innerHTML = `
            <div style="margin-bottom:20px;">
                <label style="display:block;margin-bottom:8px;font-weight:bold;">Programa:</label>
                <select id="programaSelect" onchange="cargarMateriasPorPrograma()"
                    style="width:100%;padding:10px;border-radius:8px;border:1px solid #ddd;margin-bottom:15px;">
                    ${options}
                </select>
                <button class="btn-primary" onclick="mostrarModalMateria()">+ Nueva Materia</button>
            </div>
            <div id="materiasList">
                <p style="text-align:center;padding:40px;color:#666;">Seleccione un programa para ver su malla</p>
            </div>`;
    } catch(e) {
        document.getElementById('content').innerHTML = '<p>Error cargando materias</p>';
        console.error(e);
    }
}

async function cargarMateriasPorPrograma() {
    const codigo = document.getElementById('programaSelect').value;
    if (!codigo) return;
    currentProgramaId = codigo;

    try {
        const res = await fetch(`${API_BASE}/admin/programas/${codigo}`);
        const programa = await res.json();

        // Agrupar por nivel
        const porNivel = {};
        for (const mat of (programa.materias || [])) {
            if (!porNivel[mat.nivel]) porNivel[mat.nivel] = [];
            porNivel[mat.nivel].push(mat);
        }
        const niveles = Object.keys(porNivel).map(Number).sort((a, b) => a - b);

        let html = `<h2 style="color:#1A1FC8;margin-bottom:20px;">${programa.codigo} — ${programa.nombre}</h2>`;

        if (niveles.length === 0) {
            html += '<p style="text-align:center;padding:40px;color:#666;">Sin materias registradas</p>';
        } else {
            html += '<div style="display:flex;flex-direction:column;gap:20px;">';
            for (const nivel of niveles) {
                html += `
                    <div style="background:white;border-radius:16px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                        <div style="background:linear-gradient(135deg,#1A1FC8,#0f1490);color:white;padding:12px 20px;">
                            <strong>Semestre ${nivel}</strong>
                            <span style="margin-left:10px;font-size:12px;opacity:.8;">${porNivel[nivel].length} materias</span>
                        </div>
                        <div style="padding:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;">`;

                for (const mat of porNivel[nivel]) {
                    const bg = mat.es_practica ? '#FFF3E0' : mat.es_proyecto ? '#E8F5E9' : 'white';
                    html += `
                        <div style="border:1px solid #e0e0e0;border-radius:12px;padding:12px;background:${bg};">
                            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                                <div style="flex:1;">
                                    <span style="background:#1A1FC8;color:white;padding:2px 8px;border-radius:12px;font-size:10px;">${mat.codigo}</span>
                                    ${mat.es_practica ? '<span style="background:#FF9800;color:white;padding:2px 8px;border-radius:12px;font-size:10px;margin-left:4px;">Practica</span>' : ''}
                                    ${mat.es_proyecto ? '<span style="background:#4CAF50;color:white;padding:2px 8px;border-radius:12px;font-size:10px;margin-left:4px;">Proyecto</span>' : ''}
                                    <strong style="display:block;margin:6px 0;font-size:13px;">${mat.nombre}</strong>
                                    <span style="font-size:11px;color:#666;">${mat.creditos} creditos</span>
                                    ${mat.prerrequisitos && mat.prerrequisitos.length > 0
                                        ? `<span style="font-size:11px;color:#999;margin-left:8px;">Req: ${mat.prerrequisitos.join(', ')}</span>`
                                        : ''}
                                </div>
                                <div style="display:flex;flex-direction:column;gap:5px;margin-left:8px;">
                                    <button onclick="mostrarModalEditarMateria('${mat.codigo}')" style="background:#4CAF50;color:white;border:none;border-radius:6px;padding:4px 8px;cursor:pointer;font-size:11px;">Editar</button>
                                    <button onclick="eliminarMateria('${mat.codigo}')" style="background:#ff4444;color:white;border:none;border-radius:6px;padding:4px 8px;cursor:pointer;font-size:11px;">Eliminar</button>
                                </div>
                            </div>
                        </div>`;
                }
                html += '</div></div>';
            }
            html += '</div>';
        }

        document.getElementById('materiasList').innerHTML = html;
    } catch(e) {
        document.getElementById('materiasList').innerHTML = '<p style="color:red;">Error cargando malla</p>';
        console.error(e);
    }
}

function mostrarModalMateria() {
    if (!currentProgramaId) { alert('Seleccione un programa primero'); return; }
    _abrirModalMateria('Nueva Materia', {}, false);
}

async function mostrarModalEditarMateria(materiaCodigo) {
    try {
        const res = await fetch(`${API_BASE}/admin/programas/${currentProgramaId}`);
        const prog = await res.json();
        const mat = prog.materias.find(m => m.codigo === materiaCodigo);
        if (!mat) { alert('Materia no encontrada'); return; }
        _abrirModalMateria('Editar Materia', mat, true);
    } catch(e) { alert('Error cargando materia'); }
}

function _abrirModalMateria(titulo, mat, esEdicion) {
    const div = document.createElement('div');
    div.id = 'wrapperModalMateria';
    div.innerHTML = `
        <div style="display:flex;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);justify-content:center;align-items:center;z-index:1000;">
            <div style="background:white;padding:30px;border-radius:16px;width:500px;max-width:90%;max-height:90%;overflow-y:auto;">
                <h2 style="margin-bottom:20px;color:#1A1FC8;">${titulo}</h2>
                <input id="mCodigo"  type="text"   placeholder="Codigo"         value="${mat.codigo  || ''}" style="width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:6px;">
                <input id="mNombre"  type="text"   placeholder="Nombre"         value="${mat.nombre  || ''}" style="width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:6px;">
                <input id="mCreditos" type="number" placeholder="Creditos"      value="${mat.creditos || ''}" style="width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:6px;">
                <input id="mNivel"   type="number" placeholder="Semestre"       value="${mat.nivel   || ''}" style="width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:6px;">
                <input id="mPrereqs" type="text"   placeholder="Prereqs (separados por coma)" value="${(mat.prerrequisitos || []).join(', ')}" style="width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:6px;">
                <div style="display:flex;gap:20px;margin:12px 0;">
                    <label><input type="checkbox" id="mProyecto" ${mat.es_proyecto ? 'checked' : ''}> Proyecto</label>
                    <label><input type="checkbox" id="mPractica" ${mat.es_practica ? 'checked' : ''}> Practica</label>
                </div>
                <div style="display:flex;gap:10px;margin-top:20px;">
                    <button onclick="_guardarMateria('${mat.codigo || ''}', ${esEdicion})" style="flex:1;background:#1A1FC8;color:white;padding:10px;border:none;border-radius:6px;cursor:pointer;">Guardar</button>
                    <button onclick="document.getElementById('wrapperModalMateria').remove()" style="flex:1;background:#ccc;padding:10px;border:none;border-radius:6px;cursor:pointer;">Cancelar</button>
                </div>
            </div>
        </div>`;
    document.body.appendChild(div);
}

async function _guardarMateria(codigoOriginal, esEdicion) {
    const body = {
        codigo:      document.getElementById('mCodigo').value,
        nombre:      document.getElementById('mNombre').value,
        creditos:    parseInt(document.getElementById('mCreditos').value),
        nivel:       parseInt(document.getElementById('mNivel').value),
        prerrequisitos: document.getElementById('mPrereqs').value
            .split(',').map(p => p.trim()).filter(p => p),
        es_proyecto: document.getElementById('mProyecto').checked,
        es_practica: document.getElementById('mPractica').checked,
    };

    if (!body.codigo || !body.nombre || !body.creditos || !body.nivel) {
        alert('Complete todos los campos obligatorios'); return;
    }

    try {
        let res;
        if (esEdicion) {
            res = await fetch(`${API_BASE}/admin/materias/${codigoOriginal}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
        } else {
            res = await fetch(`${API_BASE}/admin/materias?programa_id=${currentProgramaId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
        }

        if (res.ok) {
            alert(esEdicion ? 'Materia actualizada' : 'Materia creada');
            document.getElementById('wrapperModalMateria').remove();
            cargarMateriasPorPrograma();
        } else {
            const err = await res.json();
            alert('Error: ' + (err.detail || JSON.stringify(err)));
        }
    } catch(e) { alert('Error al guardar'); console.error(e); }
}

async function eliminarMateria(materiaCodigo) {
    if (!confirm(`¿Eliminar la materia ${materiaCodigo}?`)) return;
    try {
        const res = await fetch(`${API_BASE}/admin/materias/${materiaCodigo}`, { method: 'DELETE' });
        if (res.ok) { alert('Materia eliminada'); cargarMateriasPorPrograma(); }
        else alert('Error al eliminar la materia');
    } catch(e) { alert('Error al eliminar'); }
}
