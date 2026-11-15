import { app } from "../../scripts/app.js";

const types = { int: "INT", float: "FLOAT", bool: "BOOLEAN", str: "STRING" };
const defaults = { int: "0", float: "0.0", bool: false, str: "" };

function parseParameters(value, id) {
    let rows;
    try {
        rows = JSON.parse(value);
    } catch {
        throw new Error(`CustomParameters ${id}: parameters must be a JSON array. Fix the parameters widget or upstream JSON.`);
    }
    if (!Array.isArray(rows) || rows.some((row) =>
        !row || !Object.hasOwn(types, row.key) || !Object.hasOwn(row, "value"))) {
        throw new Error(`CustomParameters ${id}: each row needs key (int, float, bool, str) and value.`);
    }
    return rows;
}

// Transform only the API graph. The editable workflow retains its IDs and sockets.
function expandParameters(output) {
    const sources = new Map(Object.entries(output).filter(([, node]) =>
        node.class_type === "ICafeCustomParameters"));
    const instances = new Map();
    const reserved = new Set(Object.keys(output));
    const references = [];
    for (const node of Object.values(output)) {
        for (const [name, link] of Object.entries(node.inputs ?? {})) {
            if (!Array.isArray(link) || link.length !== 2 || !sources.has(String(link[0]))) continue;
            const id = String(link[0]);
            const index = link[1];
            if (!Number.isSafeInteger(index) || index < 0) {
                throw new Error(`CustomParameters ${id}: invalid output index ${index}. Reconnect the input ${name}.`);
            }
            references.push({ node, name, id, index });
            if (!instances.has(id)) instances.set(id, new Map());
            instances.get(id).set(index, null);
        }
    }
    for (const [id, slots] of instances) {
        const source = sources.get(id);
        const parameters = source.inputs.parameters;
        const rows = Array.isArray(parameters) ? null : parseParameters(parameters, id);
        const indices = [...slots.keys()].sort((a, b) => a - b);
        for (const index of indices) {
            if (rows && index >= rows.length && !(index === 0 && rows.length === 0)) {
                throw new Error(`CustomParameters ${id}: output ${index} has no row. Reconnect the consumer or restore the row.`);
            }
            let instanceId = id;
            if (index !== indices[0]) {
                const base = `${id}__parameter_${index}`;
                instanceId = base;
                for (let suffix = 1; reserved.has(instanceId); suffix++) instanceId = `${base}_${suffix}`;
                reserved.add(instanceId);
            }
            slots.set(index, instanceId);
        }
    }
    // Rewrite before cloning so linked parameters also use the transformed producer.
    for (const { node, name, id, index } of references) {
        node.inputs[name] = [instances.get(id).get(index), 0];
    }
    for (const [id, slots] of instances) {
        const source = sources.get(id);
        for (const [index, instanceId] of slots) {
            output[instanceId] = {
                ...source,
                inputs: {
                    ...source.inputs,
                    output_index: index === 0 ? (source.inputs.output_index ?? 0) : index,
                },
            };
        }
    }
}

app.registerExtension({
    name: "tool_nodes.CustomParameters",
    setup() {
        const graphToPrompt = app.graphToPrompt;
        app.graphToPrompt = async function (...args) {
            const prompt = await graphToPrompt.apply(this, args);
            expandParameters(prompt.output);
            return prompt;
        };
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "ICafeCustomParameters") return;
        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onCreated?.apply(this, arguments);
            const storage = this.widgets.find((widget) => widget.name === "parameters");
            storage.hidden = true;
            const selector = this.widgets.find((widget) => widget.name === "output_index");
            if (selector) selector.hidden = true;
            this.widgets_start_y = 6;
            this.parameterWidgets = [];
            this.parameterRows = parseParameters(storage.value, this.id);
            this.editingParameters = false;
            this.parameterDraft = { key: "str", value: "" };

            this.syncParameters = () => {
                storage.value = JSON.stringify(this.parameterRows);
                const draftCount = this.editingParameters ? 1 : 0;
                this.setSize([Math.max(this.size[0], 300), (this.parameterRows.length + draftCount) * 34 + 42]);
                this.setDirtyCanvas(true, true);
            };
            this.renderParameters = () => {
                for (const widget of this.parameterWidgets) this.removeWidget(widget);
                this.parameterWidgets = [];
                while (this.outputs.length > this.parameterRows.length) {
                    this.removeOutput(this.outputs.length - 1);
                }
                const rows = [...this.parameterRows];
                if (this.editingParameters) rows.push(this.parameterDraft);
                rows.forEach((row, index) => {
                    const isDraft = row === this.parameterDraft;
                    const offset = this.editingParameters ? 24 : 0;
                    const name = `parameter_${index + 1}`;
                    if (!isDraft) {
                        if (!this.outputs[index]) this.addOutput(name, types[row.key]);
                        this.outputs[index].name = name;
                        this.outputs[index].type = types[row.key];
                        this.outputs[index].label = " ";
                        this.outputs[index].pos = [
                            this.size[0] + 1 - LiteGraph.NODE_SLOT_HEIGHT / 2, 22 + index * 34,
                        ];
                    }
                    const widget = this.addCustomWidget({
                        name: `parameter_row_${index + 1}`,
                        type: "parameter_row",
                        value: null,
                        options: { serialize: false },
                        computeSize: () => [300, 30],
                        draw: (ctx, node, _widgetWidth, y) => {
                            // Widget layout width can exceed the node's canvas width.
                            const width = node.size[0];
                            const height = LiteGraph.NODE_WIDGET_HEIGHT;
                            const top = y + (30 - height) / 2;
                            const middle = y + 15;
                            if (!isDraft) {
                                node.outputs[index].pos = [
                                    width + 1 - LiteGraph.NODE_SLOT_HEIGHT / 2, middle,
                                ];
                            }
                            ctx.save();
                            ctx.beginPath();
                            ctx.rect(0, 0, width, node.size[1]);
                            ctx.clip();
                            ctx.font = app.canvas.inner_text_font;
                            ctx.textAlign = "left";
                            ctx.textBaseline = "middle";
                            ctx.fillStyle = LiteGraph.WIDGET_BGCOLOR;
                            ctx.strokeStyle = LiteGraph.WIDGET_OUTLINE_COLOR;
                            ctx.lineWidth = 1;
                            ctx.beginPath();
                            ctx.roundRect(10 + offset, top, 74, height, height / 2);
                            ctx.fill();
                            ctx.stroke();
                            ctx.beginPath();
                            ctx.roundRect(90 + offset, top, Math.max(0, width - 112 - offset), height, height / 2);
                            ctx.fill();
                            ctx.stroke();
                            ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
                            if (this.editingParameters) {
                                ctx.fillText(isDraft ? "+" : "−", 14, middle);
                            }
                            ctx.fillText(row.key, 22 + offset, middle);
                            ctx.beginPath();
                            ctx.moveTo(69 + offset, middle - 3);
                            ctx.lineTo(77 + offset, middle - 3);
                            ctx.lineTo(73 + offset, middle + 3);
                            ctx.fill();
                            ctx.beginPath();
                            ctx.rect(98 + offset, top, Math.max(0, width - 132 - offset), height);
                            ctx.clip();
                            if (isDraft && row.value === "") {
                                ctx.fillStyle = LiteGraph.WIDGET_SECONDARY_TEXT_COLOR;
                                ctx.fillText("填写值，回车添加", 98 + offset, middle);
                            } else {
                                ctx.fillText(String(row.value), 98 + offset, middle);
                            }
                            ctx.restore();
                        },
                        mouse: (event, position) => {
                            if (event.type !== "pointerdown" && event.type !== "mousedown") return false;
                            if (position[0] < 10 || position[0] > this.size[0] - 22) return false;
                            if (this.editingParameters && position[0] < 32) {
                                if (!isDraft) {
                                    this.removeOutput(index);
                                    this.parameterRows.splice(index, 1);
                                    this.renderParameters();
                                }
                                return true;
                            }
                            if (position[0] >= 10 + offset && position[0] <= 84 + offset) {
                                new LiteGraph.ContextMenu(Object.keys(types), {
                                    event,
                                    callback: (kind) => {
                                        if (kind === row.key) return;
                                        if (!isDraft) this.disconnectOutput(index);
                                        row.key = kind;
                                        row.value = defaults[kind];
                                        this.renderParameters();
                                    },
                                });
                            } else if (position[0] >= 90 + offset) {
                                if (row.key === "bool" && !isDraft) {
                                    row.value = !(row.value === true || row.value === "true");
                                    this.syncParameters();
                                } else {
                                    app.canvas.prompt(isDraft ? "填写值，回车添加" : "value", String(row.value), (value) => {
                                        if (value === null) return;
                                        if (isDraft) {
                                            if (row !== this.parameterDraft) return;
                                            if (row.key === "int" && !/^[+-]?[0-9]+$/.test(value.trim())) return;
                                            if (row.key === "float" && (!value.trim() || !Number.isFinite(Number(value)))) return;
                                            if (row.key === "bool" && !/^(true|false)$/i.test(value.trim())) return;
                                            row.value = row.key === "bool" ? value.trim().toLowerCase() === "true" : value;
                                            this.parameterRows.push(row);
                                            this.parameterDraft = { key: row.key, value: "" };
                                            this.renderParameters();
                                            return;
                                        }
                                        row.value = value;
                                        this.syncParameters();
                                    }, event);
                                }
                            }
                            return true;
                        },
                    });
                    this.parameterWidgets.push(widget);
                });
                this.parameterWidgets.push(this.addCustomWidget({
                    name: "parameter_settings",
                    type: "parameter_settings",
                    value: null,
                    options: { serialize: false },
                    computeSize: () => [300, 24],
                    draw: (ctx, node, _width, y) => {
                        ctx.save();
                        ctx.font = app.canvas.inner_text_font;
                        ctx.textBaseline = "middle";
                        ctx.textAlign = "right";
                        ctx.fillStyle = LiteGraph.WIDGET_SECONDARY_TEXT_COLOR;
                        if (this.editingParameters) {
                            ctx.fillText(`${this.parameterRows.length} · 点击齿轮完成`, node.size[0] - 46, y + 12);
                        }
                        ctx.fillStyle = LiteGraph.WIDGET_BGCOLOR;
                        ctx.strokeStyle = LiteGraph.WIDGET_OUTLINE_COLOR;
                        ctx.beginPath();
                        ctx.roundRect(node.size[0] - 38, y + 1, 26, 22, 6);
                        ctx.fill();
                        ctx.stroke();
                        ctx.textAlign = "center";
                        ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
                        ctx.fillText("⚙", node.size[0] - 25, y + 12);
                        ctx.restore();
                    },
                    mouse: (event, position) => {
                        if (event.type !== "pointerdown" && event.type !== "mousedown") return false;
                        if (position[0] < this.size[0] - 38 || position[0] > this.size[0] - 12) return false;
                        this.editingParameters = !this.editingParameters;
                        this.renderParameters();
                        return true;
                    },
                }));
                this.syncParameters();
            };
            this.renderParameters();
        };

        const onResize = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function () {
            onResize?.apply(this, arguments);
            for (const output of this.outputs ?? []) {
                if (output.pos) {
                    output.pos[0] = this.size[0] + 1 - LiteGraph.NODE_SLOT_HEIGHT / 2;
                }
            }
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            onConfigure?.apply(this, arguments);
            const storage = this.widgets.find((widget) => widget.name === "parameters");
            const rows = parseParameters(storage.value, this.id);
            this.parameterRows = rows;
            this.renderParameters();
        };
    },
});
