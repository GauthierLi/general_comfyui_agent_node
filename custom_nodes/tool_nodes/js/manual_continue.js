import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "tool_nodes.ManualContinue",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "ICafeManualContinue") return;
        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onCreated?.apply(this, arguments);
            this.pauseTokens = new Set();
            const button = this.addWidget("button", "继续", null, async () => {
                const token = this.pauseTokens.values().next().value;
                if (!token || button.disabled) return;
                button.disabled = true;
                try {
                    const response = await api.fetchApi(`/icafe/pause/${token}/continue`, { method: "POST" });
                    if (!response.ok) throw new Error("继续失败，等待可能已结束。");
                    this.pauseTokens.delete(token);
                    this.updatePauseButton();
                } catch (error) {
                    button.disabled = false;
                    app.extensionManager.toast.add({
                        severity: "error", summary: "手动继续", detail: error.message, life: 5000,
                    });
                }
                this.setDirtyCanvas(true, true);
            }, { serialize: false });
            this.updatePauseButton = () => {
                button.label = this.pauseTokens.size ? "继续 ▶" : "尚未执行到此节点";
                button.disabled = this.pauseTokens.size === 0;
                this.setDirtyCanvas(true, true);
            };
            this.updatePauseButton();
            this.setSize(this.computeSize());
        };
    },
    async setup() {
        const update = ({ node_id, token, waiting }) => {
            const node = app.graph.getNodeById(node_id);
            if (node?.comfyClass !== "ICafeManualContinue") return;
            if (waiting) node.pauseTokens.add(token);
            else node.pauseTokens.delete(token);
            node.updatePauseButton();
        };
        api.addEventListener("icafe.pause", ({ detail }) => update(detail));
        this.refreshPauses = async () => {
            try {
                const response = await api.fetchApi("/icafe/pause");
                if (!response.ok) return;
                for (const wait of await response.json()) update({ ...wait, waiting: true });
            } catch (error) {
                console.warn("无法读取手动继续节点状态。", error);
            }
        };
        api.addEventListener("reconnected", () => this.refreshPauses());
        await this.refreshPauses();
    },
    async afterConfigureGraph() {
        await this.refreshPauses?.();
    },
});
