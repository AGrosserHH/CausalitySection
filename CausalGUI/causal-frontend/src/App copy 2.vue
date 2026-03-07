<!-- App.vue -->
<template>
  <div class="app-container">

    <!-- Sidebar -->
    <aside class="sidebar">
      <h2>📊 Dataset</h2>
      <input type="file" accept=".csv" @change="handleFileUpload" style="margin-bottom: 20px;" />

      <h3>📌 Variables</h3>
      <ul style="list-style: none; padding: 0;">
        <li
          v-for="v in variables"
          :key="v.id"
          draggable="true"
          @dragstart="onDragStart(v.name, $event)"
          style="padding: 6px; margin-bottom: 5px; background: #374151; border-radius: 4px; cursor: grab;"
        >
          {{ v.name }}
        </li>
      </ul>
    </aside>

    <!-- Main Panel -->
    <main class="main-content">
      <h1 style="margin-top: 0;">🧠 Causal AI Graph Builder</h1>

      <!-- Graph & Controls -->
      <div class="graph-and-controls">
        <!-- Graph -->
        <div
          ref="cyContainer"
          class="graph-canvas"
          @dragover.prevent
          @drop="onDrop"
        ></div>

        <!-- Controls -->
        <div class="controls-panel">
          <h3>🎛️ Controls</h3>

          <label>
            Treatment:
            <select v-model="selectedTreatment" style="width: 100%;">
              <option v-for="v in variables" :key="v.id" :value="v.id">{{ v.name }}</option>
            </select>
          </label>

          <label>
            Outcome:
            <select v-model="selectedOutcome" style="width: 100%;">
              <option v-for="v in variables" :key="v.id" :value="v.id">{{ v.name }}</option>
            </select>
          </label>

          <label>
            Method:
            <select v-model="selectedMethod" style="width: 100%;">
              <option disabled value="">--Select--</option>
              <option value="backdoor.linear_regression">Backdoor: Linear Regression</option>
              <option value="backdoor.propensity_score_matching">Propensity Matching</option>
              <option value="iv.instrumental_variable">Instrumental Variable</option>
              <option value="frontdoor.two_stage_regression">2-Stage Regression</option>
            </select>
          </label>

          <button @click="saveGraph" style="padding: 8px; background: #3b82f6; color: white; border: none; border-radius: 4px;">
            💾 Save Graph
          </button>
          <button @click="computeInference" style="padding: 8px; background: #10b981; color: white; border: none; border-radius: 4px;">
            🔍 Run Inference
          </button>
        </div>
      </div>

      <!-- Inference Result -->
      <div v-if="inferenceResult !== null" class="inference-result">
        <h3>📊 Inference Result</h3>
        <p><strong>Estimated Effect:</strong> {{ inferenceResult }}</p>
        <div v-if="causalGraphImageUrl">
          <h4>📈 Causal Graph</h4>
          <img :src="causalGraphImageUrl" alt="Causal Graph" style="max-width: 100%;" />
        </div>
      </div>
    </main>
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
      selectedOutcome: null,    // ID of selected outcome variable
      selectedMethod: "", // Method for inference
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
        ;
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
          graph_id: this.graphId,
          method_name: this.selectedMethod
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
html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
  font-family: sans-serif;
}

.app-container {
  display: flex;
  height: 100vh; /* full vertical height */
  width: 100vw;  /* full horizontal width */
  overflow: hidden;
}

.sidebar {
  width: 240px;
  background-color: #1f2937;
  color: white;
  padding: 20px;
  box-sizing: border-box;
  overflow-y: auto;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 20px;
  box-sizing: border-box;
  overflow: auto;
  background: #f9fafb;
}

.graph-and-controls {
  display: flex;
  flex-direction: row;
  flex-grow: 1;
  gap: 20px;
  overflow: hidden;
}

.graph-canvas {
  flex: 1 1 0%;
  height: 100%;
  border: 2px dashed #d1d5db;
  border-radius: 6px;
  background: white;
}

.controls-panel {
  width: 280px;
  min-width: 260px;
  background-color: #f3f4f6;
  border-radius: 6px;
  padding: 12px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inference-result {
  margin-top: 16px;
  background: #ecfdf5;
  padding: 16px;
  border-radius: 6px;
}

/* Mobile fallback */
@media (max-width: 768px) {
  .graph-and-controls {
    flex-direction: column;
  }

  .controls-panel {
    width: 100%;
  }

  .graph-canvas {
    min-height: 400px;
  }
}
</style>
