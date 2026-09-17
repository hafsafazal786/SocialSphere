from neo4j import GraphDatabase
import networkx as nx

from bokeh.plotting import figure, from_networkx
from bokeh.models import HoverTool, CustomJS, TextInput
from bokeh.io import output_file, save
from bokeh.layouts import column

from pathlib import Path



# 1. NEO4J CONNECTION


URI = "neo4j://127.0.0.1:7687"
USERNAME = "neo4j"

PASSWORD = "Abcde@12345"


driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


# Test connection
with driver.session(database="neo4j") as session:

    result = session.run(
        "RETURN 'Connected to SocialSphere!' AS message"
    )

    print(result.single()["message"])



# 2. GET TWITTER NETWORK FROM NEO4J


G = nx.DiGraph()


with driver.session(database="neo4j") as session:

    result = session.run("""
        MATCH (a:User)-[:FOLLOWS]->(b:User)

        RETURN
            a[":ID"] AS source,
            b[":ID"] AS target,

            a.name AS source_name,
            b.name AS target_name,

            a.screen_name AS source_screen,
            b.screen_name AS target_screen,

            a.followers AS source_followers,
            b.followers AS target_followers

        LIMIT 100
    """)


    for record in result:

        source = record["source"]
        target = record["target"]


        # Add source user
        G.add_node(
            source,
            name=record["source_name"],
            screen_name=record["source_screen"],
            followers=record["source_followers"]
        )


        # Add target user
        G.add_node(
            target,
            name=record["target_name"],
            screen_name=record["target_screen"],
            followers=record["target_followers"]
        )


        # Add FOLLOWS relationship
        G.add_edge(source, target)


print("Network data loaded successfully!")
print("Number of nodes:", len(G.nodes))
print("Number of relationships:", len(G.edges))



# 3. CREATE BOKEH VISUALIZATION


plot = figure(
    title="SocialSphere - Twitter Network",
    width=900,
    height=700,
    tools="pan,wheel_zoom,box_zoom,reset,save"
)


network = from_networkx(
    G,
    nx.spring_layout,
    scale=2,
    center=(0, 0)
)



# 4. NODE AND EDGE TRANSPARENCY


network.node_renderer.glyph.size = 15


# Separate transparency values for search and hover
network.node_renderer.data_source.data["search_alpha"] = [
    1
] * len(G.nodes)

network.node_renderer.data_source.data["hover_alpha"] = [
    1
] * len(G.nodes)

network.edge_renderer.data_source.data["hover_alpha"] = [
    1
] * len(G.edges)


# Final alpha used by the node glyph
network.node_renderer.data_source.data["alpha"] = [
    1
] * len(G.nodes)

network.edge_renderer.data_source.data["alpha"] = [
    1
] * len(G.edges)


network.node_renderer.glyph.fill_alpha = "alpha"
network.node_renderer.glyph.line_alpha = "alpha"

network.edge_renderer.glyph.line_alpha = "alpha"


# Add network to plot
plot.renderers.append(network)



# 5. HOVER HIGHLIGHTING


highlight_callback = CustomJS(
    args=dict(
        node_source=network.node_renderer.data_source,
        edge_source=network.edge_renderer.data_source
    ),

    code="""

        const hovered_indices = cb_data.index.indices;


        // ----------------------------------------------------
        // No node is being hovered
        // ----------------------------------------------------

        if (hovered_indices.length === 0) {

            for (let i = 0; i < node_source.data.hover_alpha.length; i++) {
                node_source.data.hover_alpha[i] = 1;
            }

            for (let i = 0; i < edge_source.data.hover_alpha.length; i++) {
                edge_source.data.hover_alpha[i] = 1;
            }


            // Combine search and hover
            for (let i = 0; i < node_source.data.alpha.length; i++) {

                node_source.data.alpha[i] =
                    node_source.data.search_alpha[i] *
                    node_source.data.hover_alpha[i];

            }


            for (let i = 0; i < edge_source.data.alpha.length; i++) {

                edge_source.data.alpha[i] =
                    edge_source.data.hover_alpha[i];

            }


            node_source.change.emit();
            edge_source.change.emit();

            return;
        }


        // ----------------------------------------------------
        // Get hovered node
        // ----------------------------------------------------

        const hovered = hovered_indices[0];


        // Store connected nodes
        const connected = new Set();

        connected.add(hovered);


        // ----------------------------------------------------
        // Find connected nodes
        // ----------------------------------------------------

        for (let i = 0; i < edge_source.data.start.length; i++) {

            const start = edge_source.data.start[i];
            const end = edge_source.data.end[i];


            if (start === hovered) {
                connected.add(end);
            }


            if (end === hovered) {
                connected.add(start);
            }
        }


        // ----------------------------------------------------
        // Update hover transparency for nodes
        // ----------------------------------------------------

        for (let i = 0; i < node_source.data.index.length; i++) {

            const node_id = node_source.data.index[i];


            if (connected.has(node_id)) {

                node_source.data.hover_alpha[i] = 1;

            } else {

                node_source.data.hover_alpha[i] = 0.15;

            }
        }


        // ----------------------------------------------------
        // Update hover transparency for edges
        // ----------------------------------------------------

        for (let i = 0; i < edge_source.data.start.length; i++) {

            const start = edge_source.data.start[i];
            const end = edge_source.data.end[i];


            if (
                connected.has(start) &&
                connected.has(end)
            ) {

                edge_source.data.hover_alpha[i] = 1;

            } else {

                edge_source.data.hover_alpha[i] = 0.1;

            }
        }


        // ----------------------------------------------------
        // Combine search and hover
        // ----------------------------------------------------

        for (let i = 0; i < node_source.data.alpha.length; i++) {

            node_source.data.alpha[i] =
                node_source.data.search_alpha[i] *
                node_source.data.hover_alpha[i];

        }


        for (let i = 0; i < edge_source.data.alpha.length; i++) {

            edge_source.data.alpha[i] =
                edge_source.data.hover_alpha[i];

        }


        node_source.change.emit();
        edge_source.change.emit();

    """
)


# Hover information
hover = HoverTool(
    tooltips=[
        ("Name", "@name"),
        ("Username", "@screen_name"),
        ("Followers", "@followers")
    ],

    renderers=[network.node_renderer],

    callback=highlight_callback
)


plot.add_tools(hover)



# 6. SEARCH USERS


search_box = TextInput(
    title="Search by name or username:",
    placeholder="Type a name or username..."
)


search_callback = CustomJS(
    args=dict(
        node_source=network.node_renderer.data_source
    ),

    code="""

        const search_text =
            cb_obj.value.toLowerCase().trim();


        const names =
            node_source.data.name;

        const usernames =
            node_source.data.screen_name;

        const search_alpha =
            node_source.data.search_alpha;

        const hover_alpha =
            node_source.data.hover_alpha;

        const alpha =
            node_source.data.alpha;


        // ----------------------------------------------------
        // Search through all nodes
        // ----------------------------------------------------

        for (let i = 0; i < names.length; i++) {

            const name =
                String(names[i] || "").toLowerCase();

            const username =
                String(usernames[i] || "").toLowerCase();


            if (
                search_text === "" ||
                name.includes(search_text) ||
                username.includes(search_text)
            ) {

                search_alpha[i] = 1;

            } else {

                search_alpha[i] = 0.08;

            }
        }


        // ----------------------------------------------------
        // Combine search and hover
        // ----------------------------------------------------

        for (let i = 0; i < alpha.length; i++) {

            alpha[i] =
                search_alpha[i] *
                hover_alpha[i];

        }


        node_source.change.emit();

    """
)


search_box.js_on_change(
    "value",
    search_callback
)



# 7. SAVE VISUALIZATION


output_path = (
    Path(__file__).resolve().parent
    / "socialsphere_network.html"
)


output_file(str(output_path))


layout = column(
    search_box,
    plot
)


save(layout)


print()
print("========================================")
print("BOKEH VISUALIZATION CREATED SUCCESSFULLY!")
print("========================================")
print()
print("HTML file saved here:")
print(output_path)
print()


#closing

driver.close()