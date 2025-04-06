<!-- App.vue -->
<template>

<div class="sidebar">
    <!-- CSV File Upload (drag-and-drop or file picker) -->
    <div class="file-upload">
      <input 
        type="file" 
        accept=".csv" 
        @change="handleFileUpload" 
        placeholder="Upload CSV Dataset" 
      />
    </div>
    <!-- Sidebar variable list (populated after CSV upload) -->
    <ul>
      <li v-for="variable in variables" :key="variable.id">
        {{ variable.name }}
      </li>
    </ul>
  </div>

  <div>
    <h2>Causal AI GUI (Right-Click Directed Graph)</h2>

    <button @click="fetchVariables">Load Variables</button>
    <ul>
      <li
        v-for="(variable, idx) in variables"
        :key="variable.id"
        draggable="true"
        @dragstart="onDragStart(variable.name, $event)"
        style="cursor: move; margin: 4px; padding: 4px; background: #eef;"
      >
        {{ variable.name }}
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

  <!-- Controls below the graph: Treatment/Outcome selectors and Compute button -->
  <div class="controls">
    <label>
      Treatment: 
      <select v-model="selectedTreatment">
        <option v-for="varObj in variables" :key="varObj.id" :value="varObj.id">
          {{ varObj.name }}
        </option>
      </select>
    </label>
    <label>
      Outcome: 
      <select v-model="selectedOutcome">
        <option v-for="varObj in variables" :key="varObj.id" :value="varObj.id">
          {{ varObj.name }}
        </option>
      </select>
    </label>
    <button @click="computeInference">Compute Inference</button>
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
      causalGraphImageUrl: null,
      selectedTreatment: null, // ID of selected treatment variable
      selectedOutcome: null    // ID of selected outcome variable
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
          graph_id: this.graphId,
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
    handleFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      if (!file.name.endsWith(".csv") && file.type !== "text/csv") {
        alert("Please upload a valid CSV file.");
        return;
      }

      const formData = new FormData();
      formData.append("file", file);

      axios.post("/api/upload_csv/", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      })
      .then((res) => {
        this.graphId = res.data.graph_id; // ✅ store new graph ID
        this.variables = res.data.variables;
        this.selectedTreatment = null;
        this.selectedOutcome = null;
      })
      .catch((err) => {
        console.error("Upload failed:", err);
        alert("CSV upload failed.");
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
          treatment: this.selectedTreatment,
          outcome: this.selectedOutcome,
          graph_id: this.graphId 
        })
        .then(res => {
          console.log("Inference response:", res.data);
          const result = res.data.inference_result;
          this.inferenceResult = res.data.estimated_effect || "N/A"; // ✅ isolate the number
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
