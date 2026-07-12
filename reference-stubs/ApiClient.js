'use strict';

class ApiClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.accessToken = null;
    this.refreshToken = null;
  }

  async login(email, password) {
    const res = await fetch(`${this.baseUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error('login_failed');
    const data = await res.json();
    this.accessToken = data.access;
    this.refreshToken = data.refresh;
  }

  async _authedFetch(path, opts = {}) {
    const doFetch = () => fetch(`${this.baseUrl}${path}`, {
      ...opts,
      headers: { ...opts.headers, Authorization: `Bearer ${this.accessToken}` },
    });

    let res = await doFetch();
    if (res.status === 401) {
      await this._refresh();
      res = await doFetch();
    }
    return res;
  }

  async _refresh() {
    const res = await fetch(`${this.baseUrl}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: this.refreshToken }),
    });
    if (!res.ok) throw new Error('session_expired');
    const data = await res.json();
    this.accessToken = data.access;
  }

  // Client never computes memory/skills locally — always asks the server.
  async getMemory(query) {
    const res = await this._authedFetch(`/api/memory?query=${encodeURIComponent(query)}`);
    return (await res.json()).memory;
  }

  async updateSkills(delta) {
    const res = await this._authedFetch('/api/skills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta }),
    });
    return (await res.json()).result;
  }
}

module.exports = { ApiClient };
