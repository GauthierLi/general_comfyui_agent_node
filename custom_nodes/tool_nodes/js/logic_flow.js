import { app } from "../../scripts/app.js";

// The backend declares 20 value pairs. Show only DEFAULT_FLOW_NUM and grow on connection.
const MAX_FLOW_NUM = 20;
const DEFAULT_FLOW_NUM = 2;
// First dynamic pair per node. For loops reserve initial_value0 for index.
const FIRST = {
    "whileLoopStart": 0,
    "whileLoopEnd": 0,
    "forLoopStart": 1,
    "forLoopEnd": 1,
};

const pairIndex = (name, prefix) => {
    const match = new RegExp(`^${prefix}(\\d+)$`).exec(name ?? "");
    return match ? Number(match[1]) : -1;
};

// Trim the definition so both the node library preview and new nodes start small.
function trimDef(def, first) {
    const limit = first + DEFAULT_FLOW_NUM;
    const optional = def.input?.optional ?? {};
    for (const name of Object.keys(optional)) {
        if (pairIndex(name, "initial_value") >= limit) delete optional[name];
    }
    if (def.input_order?.optional) {
        def.input_order.optional = def.input_order.optional.filter((name) =>
            pairIndex(name, "initial_value") < limit);
    }
    const end = def.output_name.findIndex((name) => pairIndex(name, "value") >= limit);
    if (end < 0) return;
    for (const key of ["output", "output_name", "output_is_list", "output_tooltips"]) {
        if (Array.isArray(def[key])) def[key] = def[key].slice(0, end);
    }
}

function syncSlots(node, first) {
    if (node.syncingFlow) return;
    node.syncingFlow = true;
    try {
        let highest = first - 1;
        for (const input of node.inputs ?? []) {
            if (input.link != null) highest = Math.max(highest, pairIndex(input.name, "initial_value"));
        }
        for (const output of node.outputs ?? []) {
            if (output.links?.length) highest = Math.max(highest, pairIndex(output.name, "value"));
        }
        const target = Math.min(MAX_FLOW_NUM, Math.max(first + DEFAULT_FLOW_NUM, highest + 2));
        const hasValueOutputs = node.outputs.some((output) => pairIndex(output.name, "value") >= 0);
        for (let i = first; i < target; i++) {
            if (!node.inputs.some((input) => input.name === `initial_value${i}`)) {
                node.addInput(`initial_value${i}`, "*");
            }
            // Append outputs in order so the slot index matches the backend output index.
            if (hasValueOutputs && !node.outputs.some((output) => output.name === `value${i}`)) {
                node.addOutput(`value${i}`, "*");
            }
        }
        // Remove only trailing unconnected slots so existing link indices stay valid.
        for (let last = node.outputs.at(-1); last && pairIndex(last.name, "value") >= target
            && !last.links?.length; last = node.outputs.at(-1)) {
            node.removeOutput(node.outputs.length - 1);
        }
        for (let last = node.inputs.at(-1); last && pairIndex(last.name, "initial_value") >= target
            && last.link == null; last = node.inputs.at(-1)) {
            node.removeInput(node.inputs.length - 1);
        }
        node.setSize([node.size[0], node.computeSize()[1]]);
        node.setDirtyCanvas?.(true, true);
    } finally {
        node.syncingFlow = false;
    }
}

app.registerExtension({
    name: "tool_nodes.LogicFlow",
    addCustomNodeDefs(defs) {
        for (const [name, first] of Object.entries(FIRST)) {
            if (defs[name]) trimDef(defs[name], first);
        }
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!Object.hasOwn(FIRST, nodeData.name)) return;
        const first = FIRST[nodeData.name];
        for (const hook of ["onNodeCreated", "onConfigure", "onConnectionsChange"]) {
            const original = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () {
                const result = original?.apply(this, arguments);
                syncSlots(this, first);
                return result;
            };
        }
    },
});
