import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "tool_nodes.ShowText",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "ShowText") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            const widget = ComfyWidgets.STRING(
                this, "display_text", ["STRING", { multiline: true }], app,
            ).widget;
            widget.inputEl.readOnly = true;
            widget.inputEl.placeholder = "执行后在此显示文本";
            widget.options.serialize = false;
            this.size = [Math.max(this.size[0], 320), Math.max(this.size[1], 200)];
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            const widget = this.widgets.find((item) => item.name === "display_text");
            widget.value = (message.text ?? []).join("\n");
            this.setDirtyCanvas(true, true);
        };
    },
});
