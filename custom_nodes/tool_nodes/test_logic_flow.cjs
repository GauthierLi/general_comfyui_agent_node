// Run with Node; no ComfyUI server or credentials required.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
let extension;
const app = { registerExtension: (value) => { extension = value; } };
vm.runInNewContext(
    fs.readFileSync(`${__dirname}/js/logic_flow.js`, "utf8").replace(/^import .*;\n/, ""),
    { app },
);
const range = (start) => Array.from({ length: 20 - start }, (_, i) => i + start);
const optional = (start) => Object.fromEntries(range(start).map((i) => [`initial_value${i}`, ["*", {}]]));
const values = (start) => range(start).map((i) => `value${i}`);
const def = (name, required, start, fixed, inputStart = start) => ({
    name,
    input: { required, optional: optional(inputStart) },
    input_order: { required: Object.keys(required), optional: Object.keys(optional(inputStart)) },
    output_name: [...fixed, ...values(start)],
    output: [...fixed.map(() => "X"), ...values(start).map(() => "*")],
    output_is_list: Array(fixed.length + 20 - start).fill(false),
});
const defs = {
    "whileLoopStart": def("whileLoopStart", { condition: ["BOOLEAN", {}] }, 0, ["flow"]),
    "whileLoopEnd": def("whileLoopEnd", { flow: ["FLOW_CONTROL", {}], condition: ["BOOLEAN", {}] }, 0, []),
    "forLoopStart": def("forLoopStart", { total: ["INT", {}] }, 1, ["flow", "index"], 0),
    "forLoopEnd": def("forLoopEnd", { flow: ["FLOW_CONTROL", {}] }, 1, []),
    "mathInt": { name: "mathInt", input: { optional: optional(0) }, output_name: ["int"] },
};
defs["forLoopStart"].input.optional.initial_value0 = ["*", { display_name: "index" }];
extension.addCustomNodeDefs(defs);
assert.deepEqual(Object.keys(defs["whileLoopStart"].input.optional), ["initial_value0", "initial_value1"]);
assert.deepEqual(defs["whileLoopStart"].output_name, ["flow", "value0", "value1"]);
assert.equal(defs["whileLoopStart"].output_is_list.length, 3);
assert.deepEqual(defs["whileLoopEnd"].output_name, ["value0", "value1"]);
assert.deepEqual(defs["forLoopStart"].input_order.optional, ["initial_value0", "initial_value1", "initial_value2"]);
assert.deepEqual(defs["forLoopStart"].output_name, ["flow", "index", "value1", "value2"]);
assert.deepEqual(defs["forLoopEnd"].output_name, ["value1", "value2"]);
assert.equal(Object.keys(defs["mathInt"].input.optional).length, 20);

function nodeType(data) {
    class Node {
        constructor() {
            this.inputs = [...Object.keys(data.input.required), ...Object.keys(data.input.optional)]
                .map((name) => ({ name, link: null }));
            this.outputs = data.output_name.map((name) => ({ name, links: null }));
            this.size = [200, 0];
        }
        addInput(name) { this.inputs.push({ name, link: null }); }
        addOutput(name) { this.outputs.push({ name, links: null }); }
        removeInput(i) { this.inputs.splice(i, 1); }
        removeOutput(i) { this.outputs.splice(i, 1); }
        computeSize() { return [200, 30 + 20 * Math.max(this.inputs.length, this.outputs.length)]; }
        setSize(size) { this.size = size; }
    }
    extension.beforeRegisterNodeDef(Node, data);
    return Node;
}
const names = (slots) => slots.map((slot) => slot.name);

const Start = nodeType(defs["whileLoopStart"]);
const start = new Start();
start.onNodeCreated();
assert.deepEqual(names(start.outputs), ["flow", "value0", "value1"]);
start.outputs[2].links = [1];
start.onConnectionsChange();
assert.deepEqual(names(start.outputs), ["flow", "value0", "value1", "value2"]);
assert.deepEqual(names(start.inputs).slice(-1), ["initial_value2"]);
start.inputs[3].link = 5;
start.onConnectionsChange();
assert.deepEqual(names(start.outputs).slice(-1), ["value3"]);
start.inputs[3].link = null;
start.onConnectionsChange();
assert.deepEqual(names(start.outputs), ["flow", "value0", "value1", "value2"]);
start.outputs[2].links = [];
start.onConnectionsChange();
assert.deepEqual(names(start.outputs), ["flow", "value0", "value1"]);
assert.equal(start.size[1], 30 + 20 * 3);

// Saved workflows can hold all 20 slots or a connected slot in the middle.
start.inputs = ["condition", ...range(0).map((i) => `initial_value${i}`)].map((name) => ({ name, link: null }));
start.outputs = ["flow", ...values(0)].map((name) => ({ name, links: null }));
start.outputs[6].links = [9];
start.onConfigure();
assert.deepEqual(names(start.outputs), ["flow", ...values(0).slice(0, 7)]);
assert.deepEqual(start.outputs[6].links, [9]);
// Connecting the last slot repeatedly stops at 20 value outputs.
for (let i = 0; i < 25; i++) {
    start.outputs.at(-1).links = [10 + i];
    start.onConnectionsChange();
}
assert.deepEqual(names(start.outputs), ["flow", ...values(0)]);
assert.equal(start.inputs.length, 21);

const ForStart = nodeType(defs["forLoopStart"]);
const forStart = new ForStart();
forStart.onNodeCreated();
assert.deepEqual(names(forStart.outputs), ["flow", "index", "value1", "value2"]);
assert.deepEqual(names(forStart.inputs), ["total", "initial_value0", "initial_value1", "initial_value2"]);
forStart.outputs[3].links = [1];
forStart.onConnectionsChange();
assert.deepEqual(names(forStart.outputs).slice(-1), ["value3"]);

const End = nodeType(defs["forLoopEnd"]);
const end = new End();
end.onNodeCreated();
assert.deepEqual(names(end.inputs), ["flow", "initial_value1", "initial_value2"]);
end.inputs[2].link = 3;
end.onConnectionsChange();
assert.deepEqual(names(end.inputs).slice(-1), ["initial_value3"]);
assert.deepEqual(names(end.outputs), ["value1", "value2", "value3"]);
console.log("PASS: trimmed defs, default slots, grow on link, trailing trim, restore, cap, for-loop index");
