import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const HARNESS_MODEL = "(harness 默认)";
const TASK_PLACEHOLDER = "留空则使用 harness 目录中的 task.md";
let models = [];

function toast(summary, detail) {
    app.extensionManager.toast.add({ severity: "error", summary, detail, life: 5000 });
}

async function getJson(url) {
    const response = await api.fetchApi(url);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
    return data;
}

function agentNodes() {
    return app.graph.nodes.filter((node) => node.comfyClass === "AgentNode");
}

function widget(node, name) {
    return node.widgets.find((item) => item.name === name);
}

function applyModels(node) {
    widget(node, "model").options.values = [HARNESS_MODEL, ...models];
}

async function refreshModels(harness) {
    models = await getJson(`/agent/models?harness=${encodeURIComponent(harness)}`);
    agentNodes().forEach(applyModels);
}

function summary(info) {
    const list = (items) => (items.length ? items.join(", ") : "无");
    const env = Object.entries(info.env).map(([name, set]) => `${name} ${set ? "✔" : "✘"}`).join("  ");
    return [
        `默认 model: ${info.model || "SDK 默认"}   max_turns: ${info.max_turns}   timeout: ${info.timeout}s`,
        `prompt_mode: ${info.prompt_mode}   tools: ${list(info.tools)}`,
        `skills: ${list(info.skills)}`,
        `subagents: ${list(info.subagents)}`,
        `MCP tools: ${list(info.mcp_tools)}   plugins: ${list(info.plugins)}`,
        `常驻文本: ${info.always_on_chars} / ${info.always_on_limit} 字符`,
        `.env: ${env}`,
    ].join("\n");
}

async function updateInfo(node) {
    const name = widget(node, "harness_dir").value;
    const info = widget(node, "harness_info");
    const task = widget(node, "task");
    const requestId = (node.properties.agent_harness_info_request_id ?? 0) + 1;
    node.properties.agent_harness_info_request_id = requestId;
    if (!name) {
        info.value = "harnesses/ 下没有 harness 目录。";
        return;
    }
    node.title = `Agent: ${name}`;
    try {
        const data = await getJson(`/agent/harness_info?name=${encodeURIComponent(name)}`);
        if (
            node.properties.agent_harness_info_request_id !== requestId
            || widget(node, "harness_dir").value !== name
        ) {
            return;
        }
        info.value = summary(data);
        task.inputEl.placeholder = data.task || TASK_PLACEHOLDER;
    } catch (error) {
        if (
            node.properties.agent_harness_info_request_id !== requestId
            || widget(node, "harness_dir").value !== name
        ) {
            return;
        }
        info.value = `校验失败：${error.message}`;
        task.inputEl.placeholder = TASK_PLACEHOLDER;
    }
    node.setDirtyCanvas(true, true);
}

// 后端每次请求都重新读取 harness 目录和 .env，这里只需重新请求并刷新界面。
async function reload(node) {
    const harness = widget(node, "harness_dir");
    try {
        harness.options.values = await getJson("/agent/harnesses");
        await refreshModels(harness.value);
    } catch (error) {
        toast("重新加载失败", error.message);
    }
    await updateInfo(node);
}

// 拖动 task 和 harness_info 文本框的下边缘，调整高度。最后一个文本框 trajectory_live 占用剩余空间。
// 高度保存在 node.properties.agent_heights 中，随工作流保存。
const RESIZABLE = ["task", "harness_info"];
const EDGE = 8;
const MIN_HEIGHT = 40;

function makeResizable(node, name) {
    const target = widget(node, name);
    const el = target.inputEl;
    // 加载工作流时 configure 会替换 properties，所以每次读取都重新取对象。
    const heights = () => (node.properties.agent_heights ??= {});
    target.options.getMinHeight = () => heights()[name];
    target.options.getMaxHeight = () => heights()[name];
    const nearEdge = (event) => el.getBoundingClientRect().bottom - event.clientY <= EDGE;
    el.addEventListener("pointermove", (event) => {
        el.style.cursor = nearEdge(event) ? "row-resize" : "";
    });
    el.addEventListener("pointerdown", (event) => {
        if (!nearEdge(event)) return;
        event.preventDefault();
        event.stopPropagation();
        const startY = event.clientY;
        const startHeight = target.computedHeight;
        const move = (moveEvent) => {
            const delta = (moveEvent.clientY - startY) / app.canvas.ds.scale;
            heights()[name] = Math.max(MIN_HEIGHT, startHeight + delta);
            node.setDirtyCanvas(true, true);
        };
        const up = () => {
            document.removeEventListener("pointermove", move);
            document.removeEventListener("pointerup", up);
        };
        document.addEventListener("pointermove", move);
        document.addEventListener("pointerup", up);
    });
}

// 在文本框上方插入一行标题，标题上沿画分界线。标题行高度固定，不参与文本框的高度分配。
const SECTIONS = { task: "任务 task", harness_info: "harness 概要", trajectory_live: "实时 trajectory" };

function addSectionTitle(node, name) {
    const title = node.addCustomWidget({
        name: `${name}_title`,
        type: "agent_section_title",
        value: null,
        options: { serialize: false },
        computeSize: () => [0, 24],
        draw: (ctx, drawNode, _widgetWidth, y) => {
            const width = drawNode.size[0];
            ctx.save();
            ctx.strokeStyle = LiteGraph.WIDGET_OUTLINE_COLOR;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(10, y + 4);
            ctx.lineTo(width - 10, y + 4);
            ctx.stroke();
            ctx.font = app.canvas.inner_text_font;
            ctx.textAlign = "left";
            ctx.textBaseline = "middle";
            ctx.fillStyle = LiteGraph.WIDGET_SECONDARY_TEXT_COLOR;
            ctx.fillText(SECTIONS[name], 14, y + 15);
            ctx.restore();
        },
    });
    node.widgets.splice(node.widgets.indexOf(title), 1);
    node.widgets.splice(node.widgets.indexOf(widget(node, name)), 0, title);
}

app.registerExtension({
    name: "general_cc_agent.AgentNode",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "AgentNode") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            const harness = widget(this, "harness_dir");
            const callback = harness.callback;
            harness.callback = (...args) => {
                callback?.apply(harness, args);
                updateInfo(this);
            };
            // 标题按钮默认画在右上角，这里改画到折叠圆点右侧，点击区域随绘制位置更新。
            const button = this.addTitleButton({ name: "reload_harness", text: "↻", fontSize: 16 });
            const draw = button.draw.bind(button);
            button.draw = (ctx, x, y) => {
                ctx.fillStyle = LiteGraph.NODE_TITLE_COLOR;
                draw(ctx, LiteGraph.NODE_TITLE_HEIGHT - 6, y);
            };
            const info = ComfyWidgets.STRING(this, "harness_info", ["STRING", { multiline: true }], app).widget;
            info.inputEl.readOnly = true;
            info.options.serialize = false;
            const live = ComfyWidgets.STRING(this, "trajectory_live", ["STRING", { multiline: true }], app).widget;
            live.inputEl.readOnly = true;
            live.inputEl.placeholder = "运行时在此实时显示 trajectory";
            live.options.serialize = false;
            RESIZABLE.forEach((name) => makeResizable(this, name));
            Object.keys(SECTIONS).forEach((name) => addSectionTitle(this, name));
            applyModels(this);
            this.size = [Math.max(this.size[0], 420), Math.max(this.size[1], 560)];
            updateInfo(this);
        };

        const onTitleButtonClick = nodeType.prototype.onTitleButtonClick;
        nodeType.prototype.onTitleButtonClick = function (button, canvas) {
            if (button.name === "reload_harness") reload(this);
            else onTitleButtonClick?.call(this, button, canvas);
        };

        // 标题文字右移，给左上角的重新加载按钮留出位置。
        nodeType.prototype.onDrawTitleText = function (ctx, titleHeight, size, scale, font, selected) {
            ctx.font = font;
            ctx.fillStyle = selected ? LiteGraph.NODE_SELECTED_TITLE_COLOR : LiteGraph.NODE_TITLE_COLOR;
            ctx.textAlign = "left";
            ctx.fillText(this.getTitle(), titleHeight + 16, LiteGraph.NODE_TITLE_TEXT_Y - titleHeight);
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            onConfigure?.apply(this, arguments);
            updateInfo(this);
        };
    },
    setup() {
        api.addEventListener("agent.trajectory", ({ detail }) => {
            const node = app.graph.getNodeById(detail.node_id);
            if (node?.comfyClass !== "AgentNode") return;
            const live = widget(node, "trajectory_live");
            const text = detail.lines.join("\n");
            live.value = detail.reset || !live.value ? text : `${live.value}\n${text}`;
            live.inputEl.scrollTop = live.inputEl.scrollHeight;
            node.setDirtyCanvas(true, true);
        });
    },
    async afterConfigureGraph() {
        // 模型列表用第一个 Agent 节点所选 harness 的 .env 查询一次。
        const harness = agentNodes()[0] && widget(agentNodes()[0], "harness_dir").value;
        if (!harness || models.length) return;
        try {
            await refreshModels(harness);
        } catch (error) {
            console.warn("Agent 节点无法查询模型列表。", error);
        }
    },
});
