<!-- App.vue -->
<template>
  <div>
    <h2>Causal AI GUI (Right-Click Directed Graph)</h2>

    <button @click="fetchVariables">Load Variables</button>
    <ul>
      <li
        v-for="(varName, idx) in variables"
        :key="idx"
        draggable="true"
        @dragstart="onDragStart(varName, $event)"
        style="cursor: move; margin: 4px; padding: 4px; background: #eef;"
      >
        {{ varName }}
      </li>
    </ul>

    <div
      ref="cyContainer"
      style="width: 600px; height: 400px; border: 1px solid #ccc;"
      @dragover.prevent
      @drop="onDrop"
    ></div>

    <button @click="saveGraph">💾 Save Graph</button>
    <button @click="computeInference">🔍 Compute Inference</button>

    <div v-if="inferenceResult !== null" style="margin-top: 20px;">
      <h3>Inference Result</h3>
      <p><strong>Estimated Effect:</strong> {{ inferenceResult }}</p>
    </div>

    <div v-if="causalGraphImageUrl" style="margin-top: 20px;">
      <h3>Graph Visualization</h3>
      <img :src="causalGraphImageUrl" alt="Causal Graph" style="max-width: 100%; border: 1px solid #ccc;" />
    </div>
  </div>
</template>

<script>
import axios from "axios";
import cytoscape from "cytoscape";

export default {
  name: "App",
  data() {
    return {
      variables: [],
      cy: null,
      startNode: null,
      endNode: null,
      graphId: null,
      inferenceResult: null,
      causalGraphImageUrl: null
    };
  },
  mounted() {
    this.cy = cytoscape({
      container: this.$refs.cyContainer,
      elements: [],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": "#66B",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#888",
            "target-arrow-color": "#888",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
          },
        },
      ],
      layout: { name: "grid" },
    });

    // Right-click drag events
    this.cy.on("cxttapstart", "node", (evt) => {
      this.startNode = evt.target;
      this.endNode = null;
      evt.originalEvent.preventDefault();
    });

    this.cy.on("cxtdragover", "node", (evt) => {
      if (this.startNode) {
        this.endNode = evt.target;
      }
    });

    this.cy.on("cxttapend", () => {
      if (this.startNode && this.endNode && this.startNode !== this.endNode) {
        this.cy.add({
          group: "edges",
          data: {
            source: this.startNode.id(),
            target: this.endNode.id(),
          },
        });
      }
      this.startNode = null;
      this.endNode = null;
    });

    // Delete on left-click
    this.cy.on("tap", "edge", (evt) => evt.target.remove());
    this.cy.on("tap", "node", (evt) => evt.target.remove());
  },
  methods: {
    fetchVariables() {
      axios
        .get("/api/variables/")
        .then((res) => {
          this.variables = res.data;
        })
        .catch((err) => console.error(err));
    },
    onDragStart(varName, event) {
      event.dataTransfer.setData("text/plain", varName);
      event.dataTransfer.dropEffect = "copy";
    },
    onDrop(event) {
      const varName = event.dataTransfer.getData("text/plain");
      if (varName) {
        const rect = this.$refs.cyContainer.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;

        // 🚨 Use varName directly as the ID — no suffix
        const baseId = varName;

        // Prevent duplicates
        if (this.cy.getElementById(baseId).length === 0) {
          this.cy.add({
            group: "nodes",
            data: {
              id: baseId,
              label: varName
            },
            position: { x, y }
          });
        }
      }
    },
    saveGraph() {
      const edges = this.cy.edges().map(edge => ({
        source: edge.data("source"),
        target: edge.data("target"),
        directed: true
      }));

      axios
        .post("/api/save_graph/", {
          name: "UserGraph",
          edges
        })
        .then(res => {
          this.graphId = res.data.graph_id;
          alert(`Graph saved with ID = ${this.graphId}`);
        })
        .catch(err => {
          console.error(err);
          alert("Failed to save graph");
        });
    },
    computeInference() {
      const nodeIds = this.cy.nodes().map(n => n.id());
      if (nodeIds.length < 2) {
        alert("At least two nodes are required.");
        return;
      }

      const [treatment, outcome] = nodeIds;

      axios
        .post("/api/causal_inference/", {
          treatment,
          outcome,
          graph_id: this.graphId || 1
        })
        .then(res => {
          this.inferenceResult = res.data.estimated_effect;
          this.causalGraphImageUrl = res.data.graph_image;
        })
        .catch(err => {
          console.error(err);
          alert("Causal inference failed.");
        });
    }
  }
};
</script>

<style>
body {
  font-family: sans-serif;
}
</style>
