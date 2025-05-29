# views.py

import os
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Variable, CausalGraph, CausalEdge
from dowhy import CausalModel
import os
import pandas as pd
from django.conf import settings
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
import logging
logger = logging.getLogger('causal')

#from .models import Graph, Variable


# Load the dataset (update path if needed)
#DATA_PATH = os.path.join(settings.BASE_DIR, "data.csv")
#df = pd.read_csv(DATA_PATH) if os.path.exists(DATA_PATH) else pd.DataFrame()

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def upload_csv(request):
    """Upload a CSV, create a new graph, extract variables, and store the DataFrame."""
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({"error": "No file provided."}, status=400)

    if not file_obj.name.lower().endswith('.csv'):
        return Response({"error": "Only CSV files are accepted."}, status=400)

    # Step 1: Create a new graph
    graph = CausalGraph.objects.create(name=f"Graph from {file_obj.name}")
    graph.data_file.save(file_obj.name, file_obj, save=True)

    # Step 2: Parse full CSV
    try:
        df = pd.read_csv(graph.data_file.path)
    except Exception as e:
        return Response({"error": f"Could not parse CSV: {str(e)}"}, status=400)

    # Step 3: Extract and store variables
    columns = list(df.columns)
    if not columns:
        return Response({"error": "CSV has no columns."}, status=400)

    variables = []
    for col in columns:
        var = Variable.objects.create(name=col, graph=graph)
        variables.append({"id": var.id, "name": var.name})

    # Optional: return preview of first few rows for frontend display
    preview_data = df.head(3).to_dict(orient="records")
    print(preview_data )
    
    return Response({
        "graph_id": graph.id,
        "graph_name": graph.name,
        "variables": variables,
        "preview": preview_data  # optional preview
    })

@api_view(['GET'])
def get_variables(request):
    """
    Returns only clean variable names (dataset columns).
    Filters out names like 'age_12345678'.
    """
    variables = Variable.objects.exclude(name__regex=r'.*_\d+$')
    names = variables.values_list('name', flat=True).distinct()
    return Response(list(names))

@api_view(['POST'])
def save_graph(request):
    graph_id = request.data.get("graph_id")
    name = request.data.get("name", "Unnamed Graph")
    edges = request.data.get("edges", [])

    if graph_id:
        try:
            graph = CausalGraph.objects.get(id=graph_id)
            graph.name = name
            graph.save()
        except CausalGraph.DoesNotExist:
            return Response({"error": "Graph not found."}, status=404)
    else:
        graph = CausalGraph.objects.create(name=name)

    # Remove existing edges to avoid duplicates
    graph.edges.all().delete()

    for edge in edges:
        source_name = edge["source"]
        target_name = edge["target"]
        directed = edge.get("directed", True)

        try:
            source_var = Variable.objects.get(name=source_name, graph=graph)
            target_var = Variable.objects.get(name=target_name, graph=graph)
        except Variable.DoesNotExist:
            return Response({"error": f"Variable '{source_name}' or '{target_name}' not found in this graph."}, status=400)

        CausalEdge.objects.create(
            graph=graph,
            source=source_var,
            target=target_var,
            directed=directed
        )

    return Response({"message": "Graph saved", "graph_id": graph.id})

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
import os
import pandas as pd
import numpy as np
import networkx as nx
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for image generation
import matplotlib.pyplot as plt

@api_view(['POST'])
def causal_inference(request):
    # 1. Extract and validate input parameters
    print("tgest")
    graph_id = request.data.get('graph_id')
    treatment = request.data.get('treatment')
    print(treatment)
    outcome = request.data.get('outcome')# after this line:
    graph = CausalGraph.objects.get(id=graph_id)

    # now you can safely access:
    dataset_path = graph.data_file.path
    print(dataset_path)
    if not graph_id or not treatment or not outcome or not dataset_path:
        return Response({"error": "Required parameters: graph_id, treatment, outcome, dataset"}, status=400)
    
    # 2. Locate and load the dataset CSV
    
    dataset_file = dataset_path
    if not os.path.isabs(dataset_path):
        # If a relative path is provided, assume it's under MEDIA_ROOT
        dataset_file = os.path.join(settings.MEDIA_ROOT, dataset_path)

    

    treatment_var = Variable.objects.get(id=treatment, graph=graph)
    outcome_var = Variable.objects.get(id=outcome, graph=graph)    
    
    treatment_name = treatment_var.name
    outcome_name = outcome_var.name 
    
    if not os.path.exists(dataset_file):
        print("dataset_path")
        logger.error(f"[Dataset] Failed to read dataset: {e}")
        return Response({"error": f"Dataset file not found: {dataset_path}"}, status=400)
    else:
        logger.info(f"[Request] causal_inference: graph_id={graph_id}, treatment={treatment}, outcome={outcome}")

    try:
        df = pd.read_csv(dataset_file)
        logger.info(f"[Dataset] Loaded {dataset_path}, shape={df.shape}")
        print(df)
    except Exception as e:
        print("dataset_path2")
        return Response({"error": f"Failed to read dataset: {str(e)}"}, status=400)
    # Ensure treatment and outcome columns exist in data
    if treatment_name not in df.columns or outcome_name not in df.columns:        
        return Response({"error": "Treatment or outcome variable not found in dataset."}, status=400)
    
    # conduct sanity check

    # Ensure outcome variable is binary; convert if needed
    outcome_vals = df[outcome_name].dropna().unique()

    # If not strictly binary (0 and 1), convert
    if sorted(outcome_vals) != [0, 1]:
        logger.info(f"[Outcome] Converting '{outcome_name}' to binary. Original values: {outcome_vals}")
        print(f"[INFO] Converting '{outcome_name}' to binary")

        # Most common value becomes 0, others become 1
        most_common = df[outcome_name].mode()[0]
        df[outcome_name] = df[outcome_name].apply(lambda x: 0 if x == most_common else 1)

        # Optional: log unique values after conversion
        print(f"[INFO] Outcome values after conversion: {df[outcome_name].unique()}")
        logger.info(f"[Outcome] Conversion complete. New unique values: {df[outcome_name].unique().tolist()}")

    # 3. Retrieve causal graph edges from the database
    print("graph_id")
    try:
        edges = CausalEdge.objects.filter(graph_id=graph_id)
    except Exception as e:
        return Response({"error": f"Error loading causal graph: {str(e)}"}, status=500)
    if not edges.exists():
        return Response({"error": "No causal graph found for the given graph_id."}, status=404)
    
    # 4. Build DOT-format DAG string from edges
    print("edges")
    nodes_set = set()
    dot_edges = []
    edge_list = []
    for edge in edges:
        src = edge.source.name
        tgt = edge.target.name
        nodes_set.update([src, tgt])
        edge_list.append((src, tgt))
        dot_edges.append(f'"{src}" -> "{tgt}"') # quote names to handle special chars
    dot_graph = "digraph {" + ";".join(dot_edges) + ";}"
    
    print("nodes_set =", nodes_set)
    print("treatment_name =", treatment_name)
    print("outcome_name =", outcome_name)

    # Validate that treatment and outcome are in the graph nodes
    if treatment_name not in nodes_set or outcome_name not in nodes_set:
        print("nodes_set")
        return Response({"error": "Treatment or outcome is not a node in the causal graph."}, status=400)
    else: 
        logger.debug(f"[Graph] DOT: {dot_graph}")
        logger.debug(f"[Graph] Nodes: {list(nodes_set)}")

    # Validate that all graph nodes exist as columns in the dataset
    for node in nodes_set:
        if node not in df.columns:
            return Response({"error": f"Variable '{node}' from graph not found in dataset."}, status=400)
    
    # Verify the graph is acyclic (DAG)
    G = nx.DiGraph()
    G.add_edges_from(edge_list)
    if not nx.is_directed_acyclic_graph(G):        
        logger.error(f"[Graph] Invalid DAG. Graph contains cycles.")
        return Response({"error": "The causal graph contains cycles (must be a DAG)."}, status=400)
        
    # 5. Create the CausalModel using DoWhy
    print("5. Create the CausalModel using DoWhy")
    try:
        from dowhy import CausalModel
    except ImportError:
        return Response({"error": "DoWhy library is not installed on the server."}, status=500)
    try:
        model = CausalModel(data=df, treatment=treatment_name, outcome=outcome_name, graph=dot_graph)
        print(model)
    except Exception as e:
        return Response({"error": f"Failed to create causal model: {str(e)}"}, status=400)
       
    # 6. Identify the causal effect
    print("6. Identify the causal effect")
    try:
        identified_estimand = model.identify_effect()
        print(identified_estimand)
        logger.info(f"[DoWhy] Identifying effect...")
        logger.debug(f"[DoWhy] Estimand: {identified_estimand}")
    except Exception as e:
        return Response({"error": f"Causal effect identification failed: {str(e)}"}, status=400)
    if identified_estimand is None:
        return Response({"error": "Causal effect not identifiable from the given graph."}, status=400)
    
    # 7. Choose an estimation method based on the identified estimand
    print("7. Choose an estimation method based on the identified estimand")
    method_name = None
    try:
        # Prefer backdoor adjustment if available, otherwise IV, otherwise frontdoor
        if identified_estimand.get_backdoor_variables() is not None:
            method_name = "backdoor.linear_regression"
        elif identified_estimand.get_instrumental_variables() is not None:
            method_name = "iv.instrumental_variable"
        elif identified_estimand.get_frontdoor_variables() is not None:
            method_name = "frontdoor.two_stage_regression"
            
    except Exception:
        # If any issue determining method, default to backdoor linear regression
        method_name = request.data.get("method_name")

    if not method_name:
        # fallback auto-selection based on identified_estimand
        try:
            if identified_estimand.get_backdoor_variables() is not None:
                method_name = "backdoor.linear_regression"
            elif identified_estimand.get_instrumental_variables() is not None:
                method_name = "iv.instrumental_variable"
            elif identified_estimand.get_frontdoor_variables() is not None:
                method_name = "frontdoor.two_stage_regression"
        except Exception:
            method_name = "backdoor.linear_regression"

    if method_name is None:
        return Response({"error": "No valid estimation method for the identified effect."}, status=400)
    
    print(f"Using method: {method_name}")
    
    # 8. Estimate the causal effect using the selected method
    print("8. Estimate the causal effect using the selected method")
    try:
        causal_estimate = model.estimate_effect(identified_estimand, method_name=method_name)
        print(causal_estimate)
        
        logger.info(f"[DoWhy] Estimating effect using: {method_name}")          
        logger.debug(f"[DoWhy] Causal estimate: {causal_estimate}")
        
    except Exception as e:
        print(Exception)
        logger.exception(f"[DoWhy] Estimation failed: {e}")        
        return Response({"error": f"Causal effect estimation failed: {str(e)}"}, status=400)
    
    # Extract the estimated effect value
    estimated_effect = None
    if hasattr(causal_estimate, "value"):
        estimated_effect = causal_estimate.value
        logger.debug(f"[DoWhy] Estimated effect: {estimated_effect}")
    else:
        # Fallback: try other attribute or string
        estimated_effect = getattr(causal_estimate, "estimate", str(causal_estimate))
    
    # 9. Generate and save a PNG image of the causal DAG
    print("9. Generate and save a PNG image of the causal DAG")
    try:
        pos = nx.spring_layout(G)
        plt.figure(figsize=(6, 4))
        nx.draw_networkx_nodes(G, pos, node_size=800, node_color="#a0cbe2")
        nx.draw_networkx_edges(G, pos, arrows=True, arrowstyle="->", arrowsize=10, edge_color="gray")
        nx.draw_networkx_labels(G, pos, font_size=8, font_color="black")
        plt.tight_layout()
        # Save the figure to MEDIA_ROOT/causal_graphs/
        graphs_dir = os.path.join(settings.MEDIA_ROOT, "causal_graphs")
        os.makedirs(graphs_dir, exist_ok=True)
        image_filename = f"causal_graph_{graph_id}.png"
        image_path = os.path.join(graphs_dir, image_filename)
        plt.savefig(image_path)
        plt.close()
        # Prepare image URL or relative path for response
        if hasattr(settings, "MEDIA_URL"):
            graph_image_url = settings.MEDIA_URL.rstrip("/") + "/causal_graphs/" + image_filename
            
        else:
            graph_image_url = "/media/causal_graphs/" + image_filename
        logger.info(f"[Graph] DAG saved to: {image_path}")
            
    except Exception as e:
        logger.info(f"Failed to generate graph image: {str(e)}")
        return Response({"error": f"Failed to generate graph image: {str(e)}"}, status=500)
    
    # 10. Return the results as JSON
    response_data = {
        "estimated_effect": estimated_effect,
        "method_name": method_name,
        "graph_image": graph_image_url
    }

    print(response_data)
    # Include the estimand description for reference (if needed)
    try:
        response_data["estimand_string"] = str(identified_estimand)
    except Exception:
        pass
    return Response(response_data, status=200)
