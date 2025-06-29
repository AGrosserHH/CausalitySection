<template>
  <div class="app-container">

    <!-- ✅ Intro Screen -->
    <div v-if="mode === 'home'" class="intro-screen">
      <h1>🧠 Welcome to Causality AI Platform</h1>
      <p>Please choose your data input type:</p>
      <div class="choices">
        <button @click="enterCsvMode">📄 Causality data: Upload CSV Dataset</button>
        <button @click="enterRdfMode">🌐 Causality LLM: Upload Knowledge Graph (RDF)</button>
      </div>
    </div>

    <!-- ✅ CSV Mode: Causal AI Graph Builder -->
<div v-if="mode === 'csv'" class="app-container">

  <!-- Sidebar -->
  <aside class="sidebar">
    <h2>📊 Dataset</h2>
    <input type="file" accept=".csv" @change="handleFileUpload" style="margin-bottom: 20px;" />

    <h3>📌 Variables</h3>
    <ul class="variable-list">
      <li
        v-for="v in variables"
        :key="v.id"
        draggable="true"
        @dragstart="onDragStart(v.name, $event)"
        class="variable-item"
      >
        {{ v.name }}
      </li>
    </ul>
  </aside>

  <!-- Main content -->
  <main class="main-content">
    <h1 style="margin-top: 0;">🧠 Causal AI Graph Builder</h1>

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
          <select v-model="selectedTreatment">
            <option v-for="v in variables" :key="v.id" :value="v.id">{{ v.name }}</option>
          </select>
        </label>

        <label>
          Outcome:
          <select v-model="selectedOutcome">
            <option v-for="v in variables" :key="v.id" :value="v.id">{{ v.name }}</option>
          </select>
        </label>

        <label>
          Method:
          <select v-model="selectedMethod">
            <option disabled value="">--Select--</option>
            <option value="backdoor.linear_regression">Backdoor: Linear Regression</option>
            <option value="backdoor.propensity_score_matching">Propensity Matching</option>
            <option value="iv.instrumental_variable">Instrumental Variable</option>
            <option value="frontdoor.two_stage_regression">2-Stage Regression</option>
          </select>
        </label>

        <button @click="saveGraph" class="btn-primary">💾 Save Graph</button>
        <button @click="computeInference" class="btn-success">🔍 Run Inference</button>
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

    <!-- ✅ RDF Mode -->
    <div v-if="mode === 'rdf'" class="rdf-container">
      <h2>🌐 Upload Knowledge Graph (RDF)</h2>
      <input type="file" accept=".ttl,.rdf,.xml" @change="handleRdfUpload" />

      <div v-if="rdfGraphElements.length > 0" class="rdf-graph-container">
        <h3>🔎 Visualized Knowledge Graph</h3>
        <div ref="cyRdf" class="rdf-graph-canvas"></div>
      </div>
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
      mode: "home",
      variables: [],
      cy: null,
      startNode: null,
      endNode: null,
      graphId: null,
      inferenceResult: null,
      causalGraphImageUrl: null,
      selectedTreatment: null,
      selectedOutcome: null,
      selectedMethod: "",
      rdfGraphElements: [],
    };
  },
  methods: {
    enterCsvMode() {
      this.mode = "csv";
      this.$nextTick(() => {
        this.initCytoscapeCsv();
      });
    },
    enterRdfMode() {
      this.mode = "rdf";
    },
    initCytoscapeCsv() {
      if (this.cy) this.cy.destroy();
      this.cy = cytoscape({
        container: this.$refs.cyContainer,
        elements: [],
        style: [
          { selector: "node", style: { label: "data(label)", "background-color": "#66B" } },
          { selector: "edge", style: {
              width: 2,
              "line-color": "#888",
              "target-arrow-color": "#888",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
            } }
        ],
        layout: { name: "grid" },
      });

      this.cy.on("cxttapstart", "node", (evt) => {
        this.startNode = evt.target;
        this.endNode = null;
        evt.originalEvent.preventDefault();
      });
      this.cy.on("cxtdragover", "node", (evt) => {
        if (this.startNode) this.endNode = evt.target;
      });
      this.cy.on("cxttapend", () => {
        if (this.startNode && this.endNode && this.startNode !== this.endNode) {
          this.cy.add({
            group: "edges",
            data: { source: this.startNode.id(), target: this.endNode.id() },
          });
        }
        this.startNode = null;
        this.endNode = null;
      });

      this.cy.on("tap", "edge", (evt) => evt.target.remove());
      this.cy.on("tap", "node", (evt) => evt.target.remove());
    },
    handleFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append("file", file);

      axios.post("/api/upload_csv/", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then(res => {
        this.graphId = res.data.graph_id;
        this.variables = res.data.variables;
      })
      .catch(err => {
        console.error("Upload failed:", err);
        alert("CSV upload failed.");
      });
    },
    handleRdfUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  axios.post("/api/upload_rdf/", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  })
  .then(res => {
    console.log("RDF upload response:", res.data);

    // ➔ Reset graph elements
    this.rdfGraphElements = [...res.data.nodes, ...res.data.edges];

    // ➔ Next tick to ensure DOM is updated before init
    this.$nextTick(() => {
      this.initCytoscapeRdf();
    });
  })
  .catch(err => {
    console.error("RDF upload failed:", err);
    alert("RDF upload failed.");
  });
},
    initCytoscapeRdf() {
  if (!this.$refs.cyRdf) return;

  // ➔ Destroy existing Cytoscape instance in this container if any
  if (this.cyRdf) {
    this.cyRdf.destroy();
  }

  // ➔ Initialize new instance
  this.cyRdf = cytoscape({
    container: this.$refs.cyRdf,
    elements: this.rdfGraphElements,
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "background-color": "#6b7280",
          "text-valign": "center",
          color: "white"
        }
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#9ca3af",
          "target-arrow-color": "#9ca3af",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": "10px"
        }
      }
    ],
    layout: { name: "cose" },
  });
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

        this.cy.add({
          group: "nodes",
          data: { id: varName + "_" + Date.now(), label: varName },
          position: { x, y },
        });
      }
    },
    saveGraph() {
      const edges = this.cy.edges().map(edge => ({
        source: edge.data("source"),
        target: edge.data("target"),
        directed: true
      }));

      axios.post("/api/save_graph/", {
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
    computeInference() {
      axios.post("/api/causal_inference/", {
        treatment: this.selectedTreatment,
        outcome: this.selectedOutcome,
        graph_id: this.graphId,
        method_name: this.selectedMethod
      })
      .then(res => {
        this.inferenceResult = res.data.estimated_effect || "N/A";
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
html, body, #app { height: 100%; margin: 0; padding: 0; font-family: sans-serif; }
.app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}
.intro-screen { text-align: center; margin: auto; padding: 60px; }
.choices button { margin: 10px; padding: 10px 20px; font-size: 1rem; }
.csv-container { display: flex; height: 100vh; width: 100vw; }
.sidebar {
  width: 240px;
  background-color: #1f2937;
  color: white;
  padding: 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.sidebar ul { list-style: none; padding: 0; }
.sidebar li { padding: 6px; margin-bottom: 5px; background: #374151; border-radius: 4px; cursor: grab; }
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
.inference-result { margin-top: 16px; background: #ecfdf5; padding: 16px; border-radius: 6px; }
.btn-primary { padding: 8px; background: #3b82f6; color: white; border: none; border-radius: 4px; }
.btn-success { padding: 8px; background: #10b981; color: white; border: none; border-radius: 4px; }
.rdf-upload-view { padding: 40px; }
.rdf-graph-container { margin-top: 20px; }
.rdf-graph-canvas {
  height: 600px;
  width: 100%;
  border: 1px solid #ccc;
  border-radius: 6px;
  background: white;
}
.variable-list {
  list-style: none;
  padding: 0;
}
.variable-item {
  padding: 6px;
  margin-bottom: 5px;
  background: #374151;
  border-radius: 4px;
  cursor: grab;
}
</style>
