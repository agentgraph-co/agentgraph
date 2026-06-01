# Publishing the AgentGraph SDKs

Both packages are **free** to publish (public PyPI + npm cost nothing). The only
thing needed from you is a free **auth token** for each registry. Names are
confirmed available: `agentgraph-sdk` (PyPI), `@agentgraph/trust` (npm).

You can either **(A) hand Claude the tokens** and it publishes, or **(B) run the
two commands yourself**. Both are below. ~5 minutes total, $0.

---

## Python SDK → PyPI (`agentgraph-sdk`)

**1. Get a token (one time):**
- Log in / sign up at https://pypi.org (free).
- Account settings → **API tokens** → **Add API token**.
- Name: `agentgraph-sdk`. Scope: **Entire account** (for the first publish; you can
  scope it to the project after it exists).
- Copy the token — it starts with `pypi-…`. (You only see it once.)

**2. Publish:**
- *Option A — give Claude the `pypi-…` token, and it runs the upload.*
- *Option B — run it yourself* (the wheel/sdist are already built in `sdk/dist/`):
  ```bash
  cd sdk
  python3 -m pip install --quiet twine
  python3 -m twine upload dist/*
  #   username:  __token__
  #   password:  <paste the pypi-… token>
  ```

**3. Verify:** `pip install agentgraph-sdk` (give it a couple minutes to index).

---

## JS SDK → npm (`@agentgraph/trust`)

**1. Get an account + the org + a token (one time):**
- Log in / sign up at https://www.npmjs.com (free). Verify your email.
- Create the org (claims the `@agentgraph` namespace): top-right avatar →
  **Add Organization** → name `agentgraph` → **Free** ($0).
- Account → **Access Tokens** → **Generate New Token** → type **Automation** → copy it.

**2. Publish:**
- *Option A — give Claude the npm token, and it publishes.*
- *Option B — run it yourself:*
  ```bash
  cd sdk/js
  npm login                      # or: echo "//registry.npmjs.org/:_authToken=<token>" > ~/.npmrc
  npm publish --access public    # --access public is required for scoped packages
  ```

**3. Verify:** `npm view @agentgraph/trust` (or `npm i @agentgraph/trust`).

> If you'd rather not create the `@agentgraph` org, change `name` in
> `sdk/js/package.json` to the unscoped **`agentgraph-trust`** (also available) and
> publish with plain `npm publish` — no org needed.

---

## After publishing
- Re-publishing a new version = bump `version` in `pyproject.toml` / `package.json`,
  rebuild (`python3 -m build` / `npm pack`), and run the same upload command.
- `scripts/publish_sdks.sh` runs both uploads given `PYPI_TOKEN` + `NPM_TOKEN` env vars.
