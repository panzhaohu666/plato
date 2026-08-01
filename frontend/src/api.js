const BASE = '/api'

function getToken() { return localStorage.getItem('plato_token') }

async function request(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } }
  const token = getToken()
  if (token) opts.headers['Authorization'] = `Bearer ${token}`
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opts)
  if (res.status === 401) { localStorage.removeItem('plato_token'); localStorage.removeItem('plato_user') }
  return res.json()
}

export const api = {
  login: (u, p) => request('POST', '/tenants/login/', { username: u, password: p }),
  register: (u, p) => request('POST', '/tenants/register/', { username: u, password: p }),

  createTable: (data) => request('POST', '/tables/', data),
  listTables: () => request('GET', '/tables/list/'),
  getTable: (name) => request('GET', `/tables/${name}/`),
  archiveTable: (name) => request('DELETE', `/tables/${name}/archive/`),
  addColumn: (table, data) => request('POST', `/tables/${table}/columns/`, data),

  createRow: (table, data) => request('POST', `/tables/${table}/rows/`, data),
  listRows: (table, params = '') => request('GET', `/tables/${table}/rows/list/${params}`),
  deleteRow: (table, id) => request('DELETE', `/tables/${table}/rows/${id}/delete/`),

  listSchedules: () => request('GET', '/tasks/schedules/'),
  createSchedule: (data) => request('POST', '/tasks/schedules/create/', data),
  deleteSchedule: (id) => request('DELETE', `/tasks/schedules/${id}/delete/`),

  analyzeDeps: (cols) => request('POST', '/deps/analyze/', { columns: cols }),
}

export { getToken }
