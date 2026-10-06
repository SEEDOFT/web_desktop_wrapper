const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app/scripts/wrapper_version_header.js'), 'utf8')
    .replaceAll('{{WRAPPER_VERSION}}', '1.0.1');

function fixture() {
    const calls = [];
    const events = [];
    class XHR {
        open(method, url) { this.headers = {}; this.url = url; }
        setRequestHeader(name, value) { this.headers[name] = value; }
    }
    const window = { location: new URL('https://example.test/page'), fetch(input, init) { calls.push({ input, init }); return Promise.resolve(); } };
    const document = { head: null, addEventListener: name => events.push(name) };
    const context = vm.createContext({ window, document, URL, Headers, Request, XMLHttpRequest: XHR });
    vm.runInContext(source, context);
    return { window, calls, events, context, XHR };
}

test('fetch preserves Request body and caller headers while adding one version', async () => {
    const f = fixture();
    const request = new Request('https://example.test/update', {
        method: 'POST', body: 'csrf=fixture', headers: { 'X-CSRF-Token': 'fixture', 'x-wrapper-version': 'old' }
    });
    await f.window.fetch(request);
    assert.equal(f.calls[0].input, request);
    assert.equal(f.calls[0].init.headers.get('X-CSRF-Token'), 'fixture');
    assert.equal(f.calls[0].init.headers.get('X-Wrapper-Version'), '1.0.1');
    assert.equal(await request.text(), 'csrf=fixture');
    assert.equal(request.headers.get('X-Wrapper-Version'), 'old');
});

test('external fetch and XHR receive no wrapper header; repeated injection does not wrap twice', async () => {
    const f = fixture();
    const wrapped = f.window.fetch;
    vm.runInContext(source, f.context);
    assert.equal(f.window.fetch, wrapped);
    const init = { method: 'POST', body: 'external' };
    await f.window.fetch('https://elsewhere.test/', init);
    assert.equal(f.calls[0].init, init);
    const xhr = new f.XHR();
    xhr.open('POST', '/update');
    assert.deepEqual(xhr.headers, { 'X-Wrapper-Version': '1.0.1' });
    xhr.open('GET', 'https://elsewhere.test/');
    assert.deepEqual(xhr.headers, {});
    assert.equal(f.events.includes('submit'), false);
});
