// Run with Node; no ComfyUI server or credentials required.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
let extension;
const app = { registerExtension: (value) => { extension = value; } };
vm.runInNewContext(
    fs.readFileSync(`${__dirname}/js/custom_parameters.js`, "utf8").replace(/^import .*;\n/, ""),
    { app, LiteGraph: { NODE_SLOT_HEIGHT: 20 } },
);
const rows = JSON.stringify(Array.from({ length: 100 }, (_, i) => ({ key: "int", value: String(i) })));
const source = (parameters = rows) => ({ class_type: "ICafeCustomParameters", inputs: { parameters } });
const plain = (value) => JSON.parse(JSON.stringify(value));

(async () => {
    const workflow = { nodes: [{ id: 1, outputs: Array(100).fill({}) }] };
    const output = {
        "1": source(),
        "1__parameter_99": { class_type: "Other", inputs: {} },
        "2": { class_type: "Consumer", inputs: { a: ["1", 0], b: ["1", 99], c: ["1", 99] } },
        "3": source(["1", 0]),
        "4": { class_type: "Consumer", inputs: { a: ["3", 70], b: ["3", 71] } },
    };
    const unrelated = output["1__parameter_99"];
    app.graphToPrompt = async function (arg) {
        assert.equal(this, app);
        assert.equal(arg, "export");
        return { workflow, output };
    };
    extension.setup();
    const result = await app.graphToPrompt("export");
    assert.equal(result.workflow, workflow);
    assert.equal(output["1__parameter_99"], unrelated);
    assert.deepEqual(plain(output["2"].inputs.b), ["1__parameter_99_1", 0]);
    assert.deepEqual(plain(output["2"].inputs.c), plain(output["2"].inputs.b));
    assert.equal(output["1__parameter_99_1"].inputs.output_index, 99);
    assert.equal(output["3"].inputs.output_index, 70);
    assert.deepEqual(plain(output["3__parameter_71"].inputs.parameters), ["1", 0]);
    const exported = JSON.stringify(output);
    await app.graphToPrompt("export");
    assert.equal(JSON.stringify(output), exported);

    for (const [parameters, index, valid] of [
        ["[]", 0, true], ["[]", 1, false], ["invalid", 0, false],
        ['[{"key":"bad","value":1}]', 0, false], [rows, -1, false],
    ]) {
        app.graphToPrompt = async () => ({
            output: { a: source(parameters), b: { inputs: { x: ["a", index] } } },
        });
        extension.setup();
        if (valid) await app.graphToPrompt();
        else await assert.rejects(app.graphToPrompt(), /CustomParameters a:/);
    }

    class Node {
        constructor() {
            this.widgets = [{ name: "parameters", value: rows }, { name: "output_index", value: 0 }];
            this.outputs = [{}];
            this.size = [300, 100];
            this.id = 7;
        }
        removeWidget(w) { this.widgets.splice(this.widgets.indexOf(w), 1); }
        addCustomWidget(w) { this.widgets.push(w); return w; }
        addOutput(name, type) { this.outputs.push({ name, type }); }
        removeOutput(i) { this.outputs.splice(i, 1); }
        setSize(size) { this.size = size; }
        setDirtyCanvas() {}
    }
    extension.beforeRegisterNodeDef(Node, { name: "ICafeCustomParameters", output: ["*"] });
    const node = new Node();
    node.onNodeCreated();
    assert.equal(node.outputs.length, 100);
    const socket = node.outputs[99];
    node.onConfigure();
    assert.equal(node.outputs[99], socket);
    node.widgets.find(w => w.name === "parameter_settings").mouse(
        { type: "pointerdown" }, [280, 0],
    );
    assert.equal(node.editingParameters, true);
    assert.equal(node.parameterWidgets.length, 102);
    node.widgets[0].value = "[]";
    node.onConfigure();
    assert.equal(node.outputs.length, 0);
    console.log("PASS: prompt/export, collisions, fan-out, linked inputs, repeated transform, errors, 100-row UI, restore, gear, empty rows");
})().catch((error) => { console.error(error); process.exitCode = 1; });
