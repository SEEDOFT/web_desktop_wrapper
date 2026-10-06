const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/scripts/navigation_progress.js'), 'utf8');

function fixture() {
    const documentEvents = new Map();
    const windowEvents = new Map();
    const timers = new Map();
    const microtasks = [];
    const children = [];
    let sequence = 0;
    const document = {
        documentElement: { appendChild(element) { children.push(element); element.isConnected = true; } },
        createElement() {
            return {
                properties: {}, attributes: {}, isConnected: false,
                style: { setProperty(key, value) { this[key] = value; } },
                setAttribute(key, value) { this.attributes[key] = value; },
                attachShadow() { return {}; }
            };
        },
        addEventListener(name, handler) {
            documentEvents.set(name, [...(documentEvents.get(name) || []), handler]);
        }
    };
    const window = {
        location: new URL('https://example.test/current'),
        addEventListener(name, handler) { windowEvents.set(name, handler); }
    };
    window.top = window;
    const context = vm.createContext({
        window, document, URL, Date,
        queueMicrotask: handler => microtasks.push(handler),
        setTimeout: (handler, delay) => { const id = ++sequence; timers.set(id, { handler, delay }); return id; },
        clearTimeout: id => timers.delete(id)
    });
    vm.runInContext(source, context);
    return {
        context, window, children,
        emit(name, event = {}) {
            for (const handler of documentEvents.get(name) || []) handler(event);
            while (microtasks.length) microtasks.shift()();
        },
        fire(name, event = {}) {
            for (const handler of documentEvents.get(name) || []) handler(event);
        },
        flushMicrotasks() { while (microtasks.length) microtasks.shift()(); },
        finishTimers() {
            for (const [id, entry] of [...timers]) {
                if (entry.delay < 60000) { timers.delete(id); entry.handler(); }
            }
        }
    };
}

test('Livewire navigation displays the bar immediately and hides on completion', () => {
    const f = fixture();
    assert.equal(f.children.length, 0);
    f.emit('livewire:navigate');
    const bar = f.children[0];
    assert.equal(bar.style.display, 'block');
    assert.equal(bar.style['pointer-events'], 'none');
    assert.equal(bar.attributes.role, 'progressbar');
    f.emit('livewire:navigated');
    f.finishTimers();
    assert.equal(bar.style.display, 'none');
});

test('completion before the queued start cannot leave the loading bar stuck', () => {
    const f = fixture();
    f.fire('livewire:navigate');
    f.fire('livewire:navigated');
    f.flushMicrotasks();
    assert.equal(f.children.length, 0);
});

test('failed and canceled navigation clears loading immediately', () => {
    const f = fixture();
    f.emit('livewire:navigate');
    f.emit('livewire:navigate-error');
    assert.equal(f.children[0].style.display, 'none');
    f.emit('livewire:navigate');
    f.window.__wdwNavigationProgress.cancel();
    assert.equal(f.children[0].style.display, 'none');
});

test('canceled navigation does not leave a visible bar; repeated injection has one listener', () => {
    const f = fixture();
    vm.runInContext(source, f.context);
    f.emit('livewire:navigate', { defaultPrevented: true });
    assert.equal(f.children.length, 0);
    f.emit('livewire:navigating');
    assert.equal(f.children.length, 1);
    f.emit('livewire:navigated');
    f.finishTimers();
    f.emit('livewire:navigate');
    assert.equal(f.children.length, 1);
});

test('native page links show feedback while anchor-only and modified clicks do not', () => {
    const f = fixture();
    function click(href, extra = {}) {
        const anchor = { href, target: '', hasAttribute: () => false };
        f.emit('click', { button: 0, target: { closest: () => anchor }, ...extra });
    }
    click('https://example.test/current#section');
    click('https://example.test/next', { ctrlKey: true });
    click('https://elsewhere.test/next');
    click('https://example.test/next', { defaultPrevented: true });
    assert.equal(f.children.length, 0);
    click('https://example.test/next');
    assert.equal(f.children[0].style.display, 'block');
});

test('indicator remounts if removed during a page swap', () => {
    const f = fixture();
    f.emit('livewire:navigate');
    f.children[0].isConnected = false;
    f.emit('livewire:navigating');
    assert.equal(f.children[1].style.display, 'block');
    f.emit('livewire:navigated');
    f.finishTimers();
    assert.equal(f.children[1].style.display, 'none');
});
