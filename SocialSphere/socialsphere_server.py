from neo4j import GraphDatabase
from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, HoverTool, TextInput, Button, Div, CustomJS, Select
from bokeh.plotting import figure
import networkx as nx
import base64
import os

# Neo4j connection



URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)

# Get data from Neo4j

def get_network_data():

    query = """
    MATCH (a:User)-[:FOLLOWS]->(b:User)
    WHERE a <> b
    RETURN
        a[":ID"] AS source,
        b[":ID"] AS target,
        a.name AS source_name,
        b.name AS target_name,
        a.screen_name AS source_screen,
        b.screen_name AS target_screen,
        a.followers AS source_followers,
        b.followers AS target_followers
    ORDER BY rand()
    LIMIT 1500
    """

    with driver.session(database="neo4j") as session:
        return list(session.run(query))


records = get_network_data()

# Create a balanced network

G = nx.DiGraph()

for record in records:

    source = record["source"]
    target = record["target"]

    if source is None or target is None:
        continue

    if source == target:
        continue

    if G.has_edge(source, target):
        continue

    current_nodes = set(G.nodes())

    # Add a new node only if there is still space

    new_nodes = set([source, target]) - current_nodes

    if len(current_nodes) + len(new_nodes) > 100:
        continue

    G.add_node(
        source,
        name=record["source_name"] or str(source),
        screen_name=record["source_screen"] or str(source),
        followers=record["source_followers"] or 0
    )

    G.add_node(
        target,
        name=record["target_name"] or str(target),
        screen_name=record["target_screen"] or str(target),
        followers=record["target_followers"] or 0
    )

    G.add_edge(source, target)

    # Stop when we have 100 relationships

    if G.number_of_edges() >= 100:
        break

# Create network positions

positions = nx.spring_layout(
    G,
    seed=42,
    k=2.0,
    iterations=150,
    scale=3.2
)

# Create node indexes

nodes = list(G.nodes())

node_index = {
    node: index
    for index, node in enumerate(nodes)
}

# Prepare node data

node_x = []
node_y = []
node_names = []
node_screens = []
node_followers = []
node_ids = []

for node in nodes:

    node_x.append(positions[node][0])
    node_y.append(positions[node][1])

    node_names.append(
        G.nodes[node].get("name") or str(node)
    )

    node_screens.append(
        G.nodes[node].get("screen_name") or str(node)
    )

    node_followers.append(
        G.nodes[node].get("followers") or 0
    )

    node_ids.append(str(node))

node_source = ColumnDataSource(
    data={
        "x": node_x,
        "y": node_y,
        "name": node_names,
        "screen_name": node_screens,
        "followers": node_followers,
        "id": node_ids,
        "alpha": [0.95] * len(nodes)
    }
)

# Prepare relationship data

edge_x = []
edge_y = []
edge_start = []
edge_end = []
edge_from = []
edge_to = []
edge_type = []

for source, target in G.edges():

    x1, y1 = positions[source]
    x2, y2 = positions[target]

    edge_x.append([x1, x2])
    edge_y.append([y1, y2])

    edge_start.append(node_index[source])
    edge_end.append(node_index[target])

    edge_from.append(
        G.nodes[source].get("screen_name") or str(source)
    )

    edge_to.append(
        G.nodes[target].get("screen_name") or str(target)
    )

    edge_type.append("FOLLOWS")

edge_source = ColumnDataSource(
    data={
        "xs": edge_x,
        "ys": edge_y,
        "start": edge_start,
        "end": edge_end,
        "from": edge_from,
        "to": edge_to,
        "relationship": edge_type,
        "alpha": [0.25] * len(edge_x)
    }
)

# Create network plot

network_plot = figure(
    height=680,
    width=680,
    styles={
        "position": "relative",
        "top": "-70px",
        "left": "-5px"
    },
    x_axis_location=None,
    y_axis_location=None,
    toolbar_location="right",
    tools="pan,wheel_zoom,box_zoom,reset,save",
    active_scroll="wheel_zoom",
    background_fill_color="#081522",
    border_fill_color="#081522",
    outline_line_color="#203A55",
    context_menu= None
)




network_plot.grid.visible = False

network_plot.min_border_left = 15
network_plot.min_border_right = 15
network_plot.min_border_top = 15
network_plot.min_border_bottom = 15

# Draw relationships

edge_renderer = network_plot.multi_line(
    xs="xs",
    ys="ys",
    source=edge_source,
    line_color="#49647F",
    line_width=1.2,
    line_alpha="alpha"
)

# Draw users

node_renderer = network_plot.scatter(
    x="x",
    y="y",
    source=node_source,
    size=14,
    fill_color="#38BDF8",
    fill_alpha="alpha",
    line_color="#D9F3FF",
    line_width=1
)

# Hover information

hover = HoverTool(
    renderers=[node_renderer],
    tooltips=[
        ("Name", "@name"),
        ("Username", "@screen_name"),
        ("Followers", "@followers"),
        ("User ID", "@id")
    ]
)

network_plot.add_tools(hover)

edge_hover = HoverTool(
    renderers=[edge_renderer],
    tooltips=[
        ("Relationship", "@relationship"),
        ("From", "@from"),
        ("To", "@to")
    ]
)

network_plot.add_tools(edge_hover)

# Highlight connected users

hover_callback = CustomJS(
    args={
        "node_source": node_source,
        "edge_source": edge_source
    },
    code="""
    const hovered = cb_data.index.indices;

    const node_data = node_source.data;
    const edge_data = edge_source.data;

    if (hovered.length === 0) {

        for (let i = 0; i < node_data.alpha.length; i++) {
            node_data.alpha[i] = 0.95;
        }

        for (let i = 0; i < edge_data.alpha.length; i++) {
            edge_data.alpha[i] = 0.25;
        }

    } else {

        const selected = hovered[0];
        const connected = new Set();

        connected.add(selected);

        for (let i = 0; i < edge_data.start.length; i++) {

            if (edge_data.start[i] === selected) {
                connected.add(edge_data.end[i]);
            }

            if (edge_data.end[i] === selected) {
                connected.add(edge_data.start[i]);
            }
        }

        for (let i = 0; i < node_data.alpha.length; i++) {

            if (connected.has(i)) {
                node_data.alpha[i] = 1.0;
            } else {
                node_data.alpha[i] = 0.08;
            }
        }

        for (let i = 0; i < edge_data.alpha.length; i++) {

            if (
                edge_data.start[i] === selected ||
                edge_data.end[i] === selected
            ) {
                edge_data.alpha[i] = 0.95;
            } else {
                edge_data.alpha[i] = 0.04;
            }
        }
    }

    node_source.change.emit();
    edge_source.change.emit();
    """
)

hover.callback = hover_callback

# Search controls

search_box = TextInput(
    title= "Search users",
    placeholder="Enter name, username or ID",
    height=50,
    width= 900,
    styles={
        "position": "relative",
        "top": "-70px",
        "left": "9px"
    },
    stylesheets=[
        """
        :host {
            --bk-input-background: rgba(8, 21, 34, 0.75);
            --bk-input-border-color: rgba(56, 189, 248, 0.55);
            --bk-input-focus-border-color: #38BDF8;
        }

        input {
            background: rgba(8, 21, 34, 0.75) !important;
            color: #E0F2FE !important;
            border: 1px solid rgba(56, 189, 248, 0.55) !important;
            box-shadow:
                0 0 8px rgba(56, 189, 248, 0.25),
                inset 0 0 12px rgba(56, 189, 248, 0.06) !important;
        }

        input:focus {
            border-color: #38BDF8 !important;
            box-shadow:
                0 0 8px rgba(56, 189, 248, 0.45),
                0 0 18px rgba(56, 189, 248, 0.20),
                inset 0 0 12px rgba(56, 189, 248, 0.08) !important;
            outline: none !important;
        }
        """
    ]
)

followers_filter = Select(
    title="Filter by followers",
    value="All Users",
    options=[
        "All Users",
        "100+ Followers",
        "1,000+ Followers",
        "10,000+ Followers",
        "50,000+ Followers"
    ],
    width=300,
    height=51,
    styles={"position": "relative", "top": "-72px", "left" :"40px" },
    stylesheets=[
    """
    :host {
        --bk-input-background: rgba(8, 21, 34, 0.75);
        --bk-input-border-color: rgba(56, 189, 248, 0.55);
    }

    select {
    appearance: auto !important;
    -webkit-appearance: auto !important;
    -moz-appearance: auto !important;

    background: rgba(8, 21, 34, 0.75) !important;
    color: #E0F2FE !important;

    border: 1px solid rgba(56, 189, 248, 0.55) !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.25),
        inset 0 0 12px rgba(56, 189, 248, 0.06) !important;

    padding-right: 35px !important;

}

    select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56,189,248,0.12)!important;

   }

   select:hover {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.55),
        0 0 20px rgba(56, 189, 248, 0.30),
        0 0 32px rgba(56, 189, 248, 0.12) !important;
}

select:focus {
    border-color: #38BDF8 !important;

    box-shadow:
        0 0 8px rgba(56, 189, 248, 0.45),
        0 0 18px rgba(56, 189, 248, 0.20) !important;

    outline: none !important;
}  """
]
)

search_button = Button(
    label="Search",
    button_type="primary",
    width=80,
    height=34,
    styles={"position": "relative", "top": "-54px", "left" :"9px" },
     stylesheets=[
        """
        :host {
            --button-background: #1E88D8;
        }

        button {
            background: #1E88D8 !important;
            color: #F8FAFC !important;
            border: 1px solid #38BDF8 !important;
            border-radius: 6px !important;

            box-shadow:
                0 0 6px rgba(56, 189, 248, 0.30),
                0 0 14px rgba(56, 189, 248, 0.12) !important;

            transition:
                box-shadow 0.2s ease,
                transform 0.2s ease,
                background 0.2s ease !important;
        }

        button:hover {
            background: #2499E8 !important;

            box-shadow:
                0 0 8px rgba(56, 189, 248, 0.65),
                0 0 20px rgba(56, 189, 248, 0.35),
                0 0 32px rgba(56, 189, 248, 0.15) !important;

            transform: translateY(-1px);
        }

        button:active {
            transform: translateY(0px);
        }
        """
    ]

)

clear_button = Button(
    label="Clear",
    button_type="light",
    width=80,
    height=34,
    styles={"position": "relative", "top": "-55px", "left" :"9px" },
    stylesheets=[
        """
        button {
            background: rgba(8, 21, 34, 0.75) !important;
            color: #BAE6FD !important;
            border: 1px solid rgba(56, 189, 248, 0.55) !important;
            border-radius: 6px !important;

            box-shadow:
                0 0 6px rgba(56, 189, 248, 0.20),
                0 0 14px rgba(56, 189, 248, 0.08) !important;

            transition:
                box-shadow 0.2s ease,
                transform 0.2s ease,
                background 0.2s ease !important;
        }

        button:hover {
            background: rgba(14, 42, 64, 0.90) !important;
            color: #E0F2FE !important;

            box-shadow:
                0 0 8px rgba(56, 189, 248, 0.55),
                0 0 20px rgba(56, 189, 248, 0.30),
                0 0 32px rgba(56, 189, 248, 0.12) !important;

            transform: translateY(-1px);
        }

        button:active {
            transform: translateY(0px);
        }
        """
    ]
)
    


# Search function

def apply_search():

    search_text = search_box.value.lower().strip()

    if search_text == "":

        node_source.data["alpha"] = [
            0.95 for _ in nodes
        ]

        return

    alpha_values = []

    for i in range(len(nodes)):

        name = str(
            node_source.data["name"][i]
        ).lower()

        username = str(
            node_source.data["screen_name"][i]
        ).lower()

        user_id = str(
            node_source.data["id"][i]
        ).lower()

        if (
            search_text in name
            or search_text in username
            or search_text in user_id
        ):
            alpha_values.append(1.0)
        else:
            alpha_values.append(0.08)

    node_source.data["alpha"] = alpha_values

# Clear search

def clear_search():

    search_box.value = ""

    node_source.data["alpha"] = [
        0.95 for _ in nodes
    ]

# Follower filter

def apply_filter(attr, old, new):

    selected = followers_filter.value

    alpha_values = []

    for followers in node_source.data["followers"]:

        if selected == "All Users":
            alpha_values.append(0.95)

        elif selected == "100+ Followers":
            alpha_values.append(
                0.95 if followers >= 100 else 0.08
            )

        elif selected == "1,000+ Followers":
            alpha_values.append(
                0.95 if followers >= 1000 else 0.08
            )

        elif selected == "10,000+ Followers":
            alpha_values.append(
                0.95 if followers >= 10000 else 0.08
            )

        elif selected == "50,000+ Followers":
            alpha_values.append(
                0.95 if followers >= 50000 else 0.08
            )

    node_source.data["alpha"] = alpha_values

    node_source.change.emit()

search_button.on_click(apply_search)

clear_button.on_click(clear_search)

followers_filter.on_change("value", apply_filter)

# Dataset statistics

total_users = 38986
total_relationships = 44630
visible_users = len(nodes)
visible_relationships = len(edge_start)

# Header

header = Div(
    text="""
    <div style="
        width:100%;
        background:transparent;
        position: relative;
        left: 15px;
       
       
    ">

        <div style="
    color:#F8FAFC;
    font-size:30px;
    font-weight:400;
    margin-top:5px;
    text-shadow:
        0 0 8px rgba(56, 189, 248, 0.6),
        0 0 18px rgba(56, 189, 248, 0.35),
        0 0 30px rgba(56, 189, 248, 0.2);
">
    SocialSphere
</div>

        <div style="
            color:#7F9BB7;
            font-size:13px;
            margin-top:2px;
        ">
            Interactive Social Media Network Explorer
        </div>

    </div>
    """,
    
    height=50
)

# Statistics cards

stats = Div(
    text=f"""
    <div style="
        width:168%;
        display:grid;
        grid-template-columns:repeat(4, minmax(0, 1fr));
        gap:15px;
        padding:24px 30px;
        box-sizing:border-box;
        position: relative;
        left: -25px;
        
    ">

        <div style="
            width:100%;
            height:110px;
            background:#10243A;
            border:1px solid #24415E;
            border-radius:12px;
            box-shadow:
    0 0 8px rgba(56, 189, 248, 0.12),
    0 0 18px rgba(56, 189, 248, 0.06);
            padding:20px 24px;
            box-sizing:border-box;
        ">

            <div style="
                color:#7893AE;
                font-size:11px;
                font-weight:600;
                letter-spacing:0.8px;
            ">
                TOTAL USERS
            </div>

            <div style="
                color:#F8FAFC;
                font-size:29px;
                font-weight:700;
                margin-top:9px;
            ">
                {total_users:,}
            </div>

        </div>

        <div style="
            width:100%;
            height:110px;
            background:#10243A;
            border:1px solid #24415E;
            border-radius:12px;
            padding:20px 24px;
            box-sizing:border-box;
        ">

            <div style="
                color:#7893AE;
                font-size:11px;
                font-weight:600;
                letter-spacing:0.8px;
            ">
                FOLLOW RELATIONSHIPS
            </div>

            <div style="
                color:#F8FAFC;
                font-size:29px;
                font-weight:700;
                margin-top:9px;
            ">
                {total_relationships:,}
            </div>

        </div>

        <div style="
            width:100%;
            height:110px;
            background:#10243A;
            border:1px solid #24415E;
            border-radius:12px;
            box-shadow:
    0 0 8px rgba(56, 189, 248, 0.12),
    0 0 18px rgba(56, 189, 248, 0.06);
            padding:20px 24px;
            box-sizing:border-box;
        ">

            <div style="
                color:#7893AE;
                font-size:11px;
                font-weight:600;
                letter-spacing:0.8px;
            ">
                VISIBLE USERS
            </div>

            <div style="
                color:#38BDF8;
                font-size:29px;
                font-weight:700;
                margin-top:9px;
            ">
                {visible_users}
            </div>

        </div>

        <div style="
            width:100%;
            height:110px;
            background:#10243A;
            border:1px solid #24415E;
            border-radius:12px;
            box-shadow:
    0 0 8px rgba(56, 189, 248, 0.12),
    0 0 18px rgba(56, 189, 248, 0.06);
            padding:20px 24px;
            box-sizing:border-box;
        ">

            <div style="
                color:#7893AE;
                font-size:11px;
                font-weight:600;
                letter-spacing:0.8px;
            ">
                VISIBLE LINKS
            </div>

            <div style="
                color:#7893AE;
                font-size:29px;
                font-weight:700;
                margin-top:9px;
            ">
                {visible_relationships}
            </div>

        </div>

    </div>
    """,
    sizing_mode="stretch_width",
    height=158
)

# Search section

search_section = Div(
    text="""
    <div style="
        background:#0D1D2E;
        border:1px solid #203A55;
        border-radius:12px;
        padding:18px 24px;
        box-sizing:border-box;
        width:300%;
        height: 50px;
        position : relative;
        top : -20px;
        left : 5px;
    ">

        <div style="
            color:#F8FAFC;
            font-size:15px;
            font-weight:500;
            position: relative;
            top : -10px;
            

        ">
            Network Explorer
        </div>

        <div style="
            color:#7893AE;
            font-size:15px;
            margin-top:2px;
            position: relative;
            top : -15px;

            
            
        ">
            Search for a user and explore their connections.
        </div>

    </div>
    """,
    sizing_mode="stretch_width",
    height=100
)

# Search controls

search_controls = row(
    search_box,
    search_button,
    clear_button,
    followers_filter,
    height=62

)

# Network heading

network_heading = Div(
    text="""
    <div style="
        padding:18px 2px 12px 2px;
    ">

        <div style="
            color:#F8FAFC;
            font-size:20px;
            font-weight:600;
            position : relative;
            top: -75px;
            left: 15px;
        ">
            Social Network
        </div>

        <div style="
            color:#7189A3;
            font-size:12px;
            margin-top:5px;
            position : relative;
            top : -75px;
            left : 15px;
        ">
            Explore connections between users in the Neo4j graph
        </div>

    </div>
    """,
    sizing_mode="stretch_width",
    height=70
)

# Dataset overview

dataset_panel = Div(
    text=f"""
    <div style="
        background:#10243A;
        border:1px solid #203A55;
        border-radius:12px;
        box-shadow:
    0 0 8px rgba(56, 189, 248, 0.12),
    0 0 18px rgba(56, 189, 248, 0.06);
        padding:20px;
        box-sizing:border-box;
        width:250%;
        height: 300%;
        position : relative;
        top:-731px;
        left : 750px;
    ">

        <div style="
            color:#F8FAFC;
            font-size:20px;
            font-weight:600;
            margin-bottom:14px;
        ">
            Dataset Overview
        </div>

        <div style="
            color:#7893AE;
            font-size:15px;
            line-height:2;
        ">

            <div>
                Total users
                <span style="float:right;color:#F8FAFC;">
                    {total_users:,}
                </span>
            </div>

            <div>
                FOLLOWS relationships
                <span style="float:right;color:#F8FAFC;">
                    {total_relationships:,}
                </span>
            </div>

            <div>
                Displayed users
                <span style="float:right;color:#38BDF8;">
                    {visible_users}
                </span>
            </div>

            <div>
                Displayed links
                <span style="float:right;color:#7893AE;">
                    {visible_relationships}
                </span>
            </div>

        </div>

    </div>
    """,
    sizing_mode="stretch_width",
    height=190
)

# Graph instructions

instructions_panel = Div(
    text="""
    <div style="
        background:#10243A;
        border:1px solid #203A55;
        border-radius:12px;
        box-shadow:
    0 0 8px rgba(56, 189, 248, 0.12),
    0 0 18px rgba(56, 189, 248, 0.06);
        padding:20px;
        box-sizing:border-box;
        width:180%;
        height: 800%;
        position : relative;
        top:-480px;
        left : -10px;
    ">

        <div style="
            color:#F8FAFC;
            font-size:20px;
            font-weight:600;
            margin-bottom:12px;
        ">
            Explore the graph
        </div>

        <div style="
            color:#7893AE;
            font-size:15px;
            line-height:2.1;
        ">
            Search for users using the search box.
            <br>
            Hover over a node to highlight its connections.
            <br>
            Scroll to zoom into the network.
            <br>
            Drag the graph to move around.
        </div>

    </div>
    """,
    sizing_mode="stretch_width",
    height=175
)

# Information panels

information_row = row(
    dataset_panel,
    instructions_panel,
    sizing_mode="stretch_width",
    height=190
)

# Complete dashboard

dashboard = column(
    header,
    stats,
    search_section,
    search_controls,
    network_heading,
    network_plot,
    information_row,
    sizing_mode="stretch_width",
    spacing=0
)

# Dark browser background

with open("just.jpg", "rb") as f:
    bg_image = base64.b64encode(f.read()).decode("utf-8")

curdoc().template = (
    """
{% block contents %}
<style>

html,
body {
    margin:0 !important;
    padding:0 !important;
    background:#07111F !important;
    color:#F8FAFC !important;
}

.bk-root {
    background:transparent !important;
    color:#F8FAFC !important;
}

</style>

<div style="
    width:100%;
    min-height:100vh;
    background-image:
        linear-gradient(rgba(7,17,31,0.85), rgba(7,17,31,0.85)),
        url('data:image/jpeg;base64,"""
    + bg_image +
    """');
    background-size:cover;
    background-position:center;
    background-repeat:no-repeat;
    background-attachment:fixed;
">
    {{ embed(roots.dashboard) }}
</div>

{% endblock %}
"""
)

# Add dashboard

dashboard.name = "dashboard"

curdoc().add_root(dashboard)

curdoc().title = "SocialSphere"

print("SocialSphere dashboard is ready!")
print("Total users:", total_users)
print("Total relationships:", total_relationships)
print("Visible users:", visible_users)
print("Visible relationships:", visible_relationships)