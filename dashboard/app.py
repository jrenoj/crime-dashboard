

import calendar
from functools import lru_cache

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.database import query_database


#
# Column names to look for (case-insensitive, first match wins). The app checks the
# real table at startup, so you don't need to worry about upper/lower case.
LAT_CANDIDATES = ["lat", "latitude"]
LON_CANDIDATES = ["lon", "lng", "long", "longitude"]

# Optional: an SQL expression returning the hour of day (0-23).
# Example for the LAPD "TIME OCC" field stored as HHMM: "FLOOR(time_occ / 100)"
# Leave as None to show a simple day-of-week chart instead of the day x hour grid.
HOUR_SQL = None

# Rough bounding box around LAPD's jurisdiction. Drops rows with missing (0, 0)
# coordinates, which would otherwise draw a hot spot off the coast of Africa.

LA_CENTER = {"lat": 34.05, "lon": -118.30}
LA_ZOOM = 9.4

MAX_POINTS = 10000          # most individual incidents drawn in "Individual incidents" mode
AGE_MIN, AGE_MAX = 0, 120

# Map detail = grid cell size in degrees (0.001 deg is roughly 110 m)
MAP_DETAIL = [
    {"label": "Fine", "value": 0.001},
    {"label": "Medium", "value": 0.003},
    {"label": "Coarse", "value": 0.008},
]
HEAT_RADIUS = {0.001: 8, 0.003: 14, 0.008: 26}   # blur radius in pixels per detail level

# Palette (keep in sync with assets/style.css)
INK = "#0f1b2d"
BLUE = "#1b4b8a"
MUTED = "#5f6f86"
FONT = "IBM Plex Sans, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"

DAY_NAMES = list(calendar.day_name)        # Monday first, matches ISODOW 1..7
DAY_ABBR = list(calendar.day_abbr)

# plotly >= 5.24 renamed *_mapbox functions to *_map. Support both.
if hasattr(px, "density_map"):
    density_fn, scatter_fn, STYLE_KEY = px.density_map, px.scatter_map, "map_style"
else:
    density_fn, scatter_fn, STYLE_KEY = px.density_mapbox, px.scatter_mapbox, "mapbox_style"


app = Dash(__name__, title="LA Crime Analytics")


# --------------------------------------------------
# QUERY HELPERS
# --------------------------------------------------

@lru_cache(maxsize=256)
def _cached_query(sql, params_key):
    return query_database(sql, dict(params_key))


def run(sql, params):
    """Run a query, caching by (sql, params) so repeat filter combinations are instant.
    Returned DataFrames are shared, so treat them as read-only."""
    return _cached_query(sql, tuple(sorted(params.items())))


def in_clause(expression, values, prefix, params):
    keys = []
    for i, value in enumerate(values):
        key = f"{prefix}_{i}"
        params[key] = value
        keys.append(f":{key}")
    return f"{expression} IN ({', '.join(keys)})"


def build_where(years, months, areas, crimes, weekdays, age_range):
    conditions, params = [], {}

    if years:
        conditions.append(in_clause("year", years, "year", params))
    if months:
        conditions.append(
            in_clause("EXTRACT(MONTH FROM date_occ)::INTEGER", months, "month", params)
        )
    if areas:
        conditions.append(in_clause("area_name", areas, "area", params))
    if crimes:
        conditions.append(in_clause("crime_description", crimes, "crime", params))
    if weekdays:
        conditions.append(
            in_clause("EXTRACT(ISODOW FROM date_occ)::INTEGER", weekdays, "dow", params)
        )
    # Only filter on age when the slider has actually been narrowed
    if age_range and tuple(age_range) != (AGE_MIN, AGE_MAX):
        conditions.append("victim_age BETWEEN :age_min AND :age_max")
        params["age_min"], params["age_max"] = age_range

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params


def add_condition(where, condition):
    return f"{where} AND {condition}" if where else f"WHERE {condition}"


# --------------------------------------------------
# FIGURE HELPERS
# --------------------------------------------------

def style_fig(fig):
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=8, r=8, t=8, b=8),
        font=dict(family=FONT, size=12, color=INK),
        showlegend=False,
        hoverlabel=dict(font_family=FONT, font_size=12),
    )
    return fig


def empty_figure(message):
    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(text=message, showarrow=False, font=dict(size=14, color=MUTED))],
    )
    return style_fig(fig)



_table_columns = query_database(
    """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'crime_incidents'
      AND table_schema = current_schema();
    """
)["column_name"].tolist()


def find_column(candidates, label):
    """Return the real column name, double-quoted so Postgres keeps its exact case."""
    lookup = {name.lower(): name for name in _table_columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            real_name = lookup[candidate.lower()]
            return '"' + real_name.replace('"', '""') + '"'
    raise RuntimeError(
        f"Could not find a {label} column in crime_incidents. "
        f"Columns found: {_table_columns}. Add your column name to the candidates list at the top of app.py."
    )


LAT_COL = find_column(LAT_CANDIDATES, "latitude")
LON_COL = find_column(LON_CANDIDATES, "longitude")

GEO_SQL = (
    f"{LAT_COL} BETWEEN 33.6 AND 34.5 AND "
    f"{LON_COL} BETWEEN -118.9 AND -118.0"
)


# --------------------------------------------------
# FILTER OPTIONS (loaded once at startup)
# --------------------------------------------------

years = query_database(
    "SELECT DISTINCT year FROM crime_incidents ORDER BY year;"
)["year"].tolist()

areas = query_database(
    "SELECT DISTINCT area_name FROM crime_incidents ORDER BY area_name;"
)["area_name"].tolist()

crime_types = query_database(
    "SELECT DISTINCT crime_description FROM crime_incidents ORDER BY crime_description;"
)["crime_description"].tolist()

month_options = [{"label": calendar.month_name[m], "value": m} for m in range(1, 13)]
day_options = [{"label": name, "value": i + 1} for i, name in enumerate(DAY_NAMES)]


# --------------------------------------------------
# LAYOUT
# --------------------------------------------------

CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["select2d", "lasso2d"]}


def field(label, control):
    return html.Div(
        [html.Label(label, className="field-label"), html.Div(control, className="field-control")],
        className="field",
    )


def stat(label, value_id):
    return html.Div(
        [html.Div("–", id=value_id, className="stat-value"), html.Div(label, className="stat-label")],
        className="stat",
    )


def chart_panel(title, note, graph_id, height):
    return html.Section(
        [
            html.H2(title, className="panel-title"),
            html.Div(note, className="panel-note"),
            dcc.Loading(
                dcc.Graph(id=graph_id, config=CHART_CONFIG, style={"height": f"{height}px"}),
                type="circle",
                color=BLUE,
            ),
        ],
        className="panel",
    )


when_title = "When incidents happen"
when_note = "By day of week and hour" if HOUR_SQL else "By day of week"

app.layout = html.Div(
    className="shell",
    children=[
        # ---------------- FILTER RAIL ----------------
        html.Aside(
            className="rail",
            children=html.Div(
                className="rail-inner",
                children=[
                    html.H1("LA Crime Analytics", className="brand"),
                    html.P("LAPD Reported Uncidents, 2020–2024", className="brand-sub"),
                    field("Year", dcc.Dropdown(
                        id="year-filter",
                        options=[{"label": str(y), "value": y} for y in years],
                        multi=True, placeholder="All years")),
                    field("Month", dcc.Dropdown(
                        id="month-filter", options=month_options,
                        multi=True, placeholder="All months")),
                    field("Day of week", dcc.Dropdown(
                        id="dow-filter", options=day_options,
                        multi=True, placeholder="All days")),
                    field("LAPD area", dcc.Dropdown(
                        id="area-filter", options=areas,
                        multi=True, placeholder="All areas")),
                    field("Crime type", dcc.Dropdown(
                        id="crime-filter", options=crime_types,
                        multi=True, placeholder="All crime types")),
                    field("Victim age", dcc.RangeSlider(
                        id="age-filter", min=AGE_MIN, max=AGE_MAX, step=1,
                        value=[AGE_MIN, AGE_MAX],
                        marks={a: str(a) for a in range(AGE_MIN, AGE_MAX + 1, 25)},
                        tooltip={"placement": "bottom"},
                        updatemode="mouseup")),
                    html.Button("Reset filters", id="reset-button", n_clicks=0, className="btn-reset"),
                    html.P(
                        "Tip: click a bar in the area or crime chart to add or remove it as a filter.",
                        className="rail-hint",
                    ),
                ],
            ),
        ),

        # ---------------- CONTENT ----------------
        html.Main(
            className="content",
            children=[
                html.Section(
                    className="stats",
                    children=[
                        stat("Total incidents", "kpi-total"),
                        stat("Average victim age", "kpi-age"),
                        stat("Crime types", "kpi-types"),
                        stat("Busiest area", "kpi-area"),
                    ],
                ),

                html.Section(
                    className="panel",
                    children=[
                        html.Div(
                            className="panel-head",
                            children=[
                                html.Div([
                                    html.H2("Where incidents happen", className="panel-title"),
                                    html.Div(id="map-status", className="panel-note"),
                                ]),
                                html.Div(
                                    className="map-controls",
                                    children=[
                                        dcc.RadioItems(
                                            id="map-mode",
                                            className="segmented",
                                            options=[
                                                {"label": "Density", "value": "density"},
                                                {"label": "Individual incidents", "value": "points"},
                                            ],
                                            value="density",
                                        ),
                                        dcc.RadioItems(
                                            id="map-detail",
                                            className="segmented",
                                            options=MAP_DETAIL,
                                            value=0.003,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        dcc.Loading(
                            dcc.Graph(
                                id="map-graph",
                                config={**CHART_CONFIG, "scrollZoom": True},
                                style={"height": "620px"},
                            ),
                            type="circle",
                            color=BLUE,
                        ),
                    ],
                ),

                html.Div(
                    className="grid-2",
                    children=[
                        chart_panel("Incidents over time", "Reported incidents per month", "trend-chart", 340),
                        chart_panel(when_title, when_note, "when-chart", 340),
                    ],
                ),
                html.Div(
                    className="grid-2",
                    children=[
                        chart_panel("By LAPD area", "Click a bar to filter", "area-chart", 520),
                        chart_panel("Top 15 crime types", "Click a bar to filter", "crime-chart", 520),
                    ],
                ),
            ],
        ),
    ],
)


# --------------------------------------------------
# CALLBACKS
# --------------------------------------------------

FILTER_INPUTS = [
    Input("year-filter", "value"),
    Input("month-filter", "value"),
    Input("area-filter", "value"),
    Input("crime-filter", "value"),
    Input("dow-filter", "value"),
    Input("age-filter", "value"),
]


# ---------- KPI strip ----------

@app.callback(
    Output("kpi-total", "children"),
    Output("kpi-age", "children"),
    Output("kpi-types", "children"),
    Output("kpi-area", "children"),
    *FILTER_INPUTS,
)
def update_kpis(*filters):
    where, params = build_where(*filters)

    row = run(
        f"""
        SELECT
            COUNT(*) AS total,
            AVG(victim_age) FILTER (WHERE victim_age > 0) AS avg_age,   -- ignore 0 / negative "unknown" ages
            COUNT(DISTINCT crime_description) AS crime_types,
            MODE() WITHIN GROUP (ORDER BY area_name) AS top_area
        FROM crime_incidents
        {where};
        """,
        params,
    ).iloc[0]

    avg_age = "–" if pd.isna(row["avg_age"]) else f"{float(row['avg_age']):.1f}"
    top_area = "–" if pd.isna(row["top_area"]) else row["top_area"]

    return f"{int(row['total']):,}", avg_age, f"{int(row['crime_types']):,}", top_area


# ---------- Heat map ----------

@app.callback(
    Output("map-graph", "figure"),
    Output("map-status", "children"),
    Input("map-mode", "value"),
    Input("map-detail", "value"),
    *FILTER_INPUTS,
)
def update_map(mode, cell, *filters):
    where, params = build_where(*filters)
    geo_where = add_condition(where, GEO_SQL)

    counts = run(
        f"""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE {GEO_SQL}) AS mapped
        FROM crime_incidents
        {where};
        """,
        params,
    ).iloc[0]
    total, mapped = int(counts["total"]), int(counts["mapped"])

    if mapped == 0:
        return empty_figure("No mapped incidents match these filters"), f"0 of {total:,} incidents mapped"

    status = f"{mapped:,} incidents mapped"
    if mapped < total:
        status = f"{mapped:,} of {total:,} incidents have usable coordinates and are mapped"

    # ----- Individual incidents (only when the result is small enough to draw) -----
    if mode == "points" and mapped <= MAX_POINTS:
        pts = run(
            f"""
            SELECT {LAT_COL} AS lat, {LON_COL} AS lon,
                   crime_description, area_name, date_occ
            FROM crime_incidents
            {geo_where};
            """,
            params,
        )
        fig = scatter_fn(
            pts, lat="lat", lon="lon",
            hover_name="crime_description",
            hover_data={"area_name": True, "date_occ": "|%b %d, %Y", "lat": False, "lon": False},
            color_discrete_sequence=["#e4572e"],
            opacity=0.7,
            center=LA_CENTER, zoom=LA_ZOOM,
            **{STYLE_KEY: "carto-positron"},
        )
        fig.update_traces(marker=dict(size=7))

    # ----- Density heat map, aggregated in the database -----
    else:
        if mode == "points":
            status = (
                f"{mapped:,} incidents is too many to draw individually. Showing density. "
                f"Narrow the filters to {MAX_POINTS:,} or fewer to see each incident."
            )

        # Snap every incident to a grid cell and count per cell. This turns ~1M rows
        # into a few thousand weighted points, so the browser stays fast.
        grid = run(
            f"""
            SELECT
                ROUND({LAT_COL} / CAST(:cell AS DOUBLE PRECISION)) * CAST(:cell AS DOUBLE PRECISION) AS lat,
                ROUND({LON_COL} / CAST(:cell AS DOUBLE PRECISION)) * CAST(:cell AS DOUBLE PRECISION) AS lon,
                COUNT(*) AS incidents
            FROM crime_incidents
            {geo_where}
            GROUP BY 1, 2;
            """,
            {**params, "cell": cell},
        )
        fig = density_fn(
            grid, lat="lat", lon="lon", z="incidents",
            radius=HEAT_RADIUS.get(cell, 14),
            center=LA_CENTER, zoom=LA_ZOOM,
            color_continuous_scale="YlOrRd",
            **{STYLE_KEY: "carto-positron"},
        )
        fig.update_traces(hovertemplate=None, hoverinfo="skip")
        fig.update_layout(
            coloraxis_colorbar=dict(title="Incidents", thickness=12, len=0.4, x=0.99, xanchor="right"),
        )

    style_fig(fig)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), uirevision="la-map")  # keep pan/zoom between filter changes
    return fig, status


# ---------- Charts ----------

@app.callback(
    Output("trend-chart", "figure"),
    Output("when-chart", "figure"),
    Output("area-chart", "figure"),
    Output("crime-chart", "figure"),
    *FILTER_INPUTS,
)
def update_charts(*filters):
    where, params = build_where(*filters)
    none_msg = "No incidents match these filters"

    # -- Trend by month --
    trend = run(
        f"""
        SELECT DATE_TRUNC('month', date_occ)::DATE AS month, COUNT(*) AS incidents
        FROM crime_incidents
        {where}
        GROUP BY 1 ORDER BY 1;
        """,
        params,
    )
    if trend.empty:
        return (empty_figure(none_msg),) * 4

    trend_fig = px.line(trend, x="month", y="incidents")
    trend_fig.update_traces(
        line=dict(color=BLUE, width=2),
        fill="tozeroy", fillcolor="rgba(27, 75, 138, 0.08)",
        hovertemplate="%{x|%b %Y}: %{y:,} incidents<extra></extra>",
    )
    trend_fig.update_xaxes(title=None, showgrid=False)
    trend_fig.update_yaxes(title=None, rangemode="tozero", tickformat=",")

    # -- Day of week (and hour, if configured) --
    if HOUR_SQL:
        when = run(
            f"""
            SELECT EXTRACT(ISODOW FROM date_occ)::INTEGER AS dow,
                   CAST({HOUR_SQL} AS INTEGER) AS hour,
                   COUNT(*) AS incidents
            FROM crime_incidents
            {where}
            GROUP BY 1, 2;
            """,
            params,
        )
        matrix = (
            when.pivot_table(index="dow", columns="hour", values="incidents", aggfunc="sum")
            .reindex(index=range(1, 8), columns=range(24))
            .fillna(0)
        )
        when_fig = px.imshow(
            matrix.values, x=list(range(24)), y=DAY_ABBR,
            aspect="auto", color_continuous_scale="YlOrRd",
        )
        when_fig.update_traces(hovertemplate="%{y}, %{x}:00<br>%{z:,} incidents<extra></extra>")
        when_fig.update_xaxes(title=None, dtick=3)
        when_fig.update_yaxes(title=None)
        when_fig.update_layout(coloraxis_showscale=False)
    else:
        when = run(
            f"""
            SELECT EXTRACT(ISODOW FROM date_occ)::INTEGER AS dow, COUNT(*) AS incidents
            FROM crime_incidents
            {where}
            GROUP BY 1;
            """,
            params,
        )
        counts = when.set_index("dow")["incidents"].reindex(range(1, 8)).fillna(0)
        when_fig = px.bar(x=DAY_ABBR, y=counts.values)
        when_fig.update_traces(marker_color=BLUE, hovertemplate="%{x}: %{y:,}<extra></extra>")
        when_fig.update_xaxes(title=None)
        when_fig.update_yaxes(title=None, tickformat=",")

    # -- By area --
    area = run(
        f"""
        SELECT area_name, COUNT(*) AS incidents
        FROM crime_incidents
        {where}
        GROUP BY area_name ORDER BY incidents DESC;
        """,
        params,
    )
    area_fig = px.bar(area.iloc[::-1], x="incidents", y="area_name", orientation="h")
    area_fig.update_traces(marker_color=BLUE, hovertemplate="%{y}: %{x:,}<extra></extra>")
    area_fig.update_xaxes(title=None, tickformat=",")
    area_fig.update_yaxes(title=None, dtick=1, automargin=True)

    # -- Top crime types --
    crime = run(
        f"""
        SELECT crime_description, COUNT(*) AS incidents
        FROM crime_incidents
        {where}
        GROUP BY crime_description ORDER BY incidents DESC
        LIMIT 15;
        """,
        params,
    )
    crime_fig = px.bar(crime.iloc[::-1], x="incidents", y="crime_description", orientation="h")
    crime_fig.update_traces(marker_color=BLUE, hovertemplate="%{y}: %{x:,}<extra></extra>")
    crime_fig.update_xaxes(title=None, tickformat=",")
    crime_fig.update_yaxes(title=None, dtick=1, automargin=True)

    return tuple(style_fig(f) for f in (trend_fig, when_fig, area_fig, crime_fig))


# ---------- Reset button ----------

@app.callback(
    Output("year-filter", "value"),
    Output("month-filter", "value"),
    Output("dow-filter", "value"),
    Output("area-filter", "value"),
    Output("crime-filter", "value"),
    Output("age-filter", "value"),
    Input("reset-button", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_):
    return None, None, None, None, None, [AGE_MIN, AGE_MAX]


# ---------- Click a bar to cross-filter ----------

@app.callback(
    Output("area-filter", "value", allow_duplicate=True),
    Output("crime-filter", "value", allow_duplicate=True),
    Output("area-chart", "clickData"),    # cleared after each click so the same bar can be clicked again
    Output("crime-chart", "clickData"),
    Input("area-chart", "clickData"),
    Input("crime-chart", "clickData"),
    State("area-filter", "value"),
    State("crime-filter", "value"),
    prevent_initial_call=True,
)
def cross_filter(area_click, crime_click, selected_areas, selected_crimes):
    source = ctx.triggered_id
    click = area_click if source == "area-chart" else crime_click
    if not click:
        raise PreventUpdate      # this is the "cleared" call from our own reset of clickData

    label = click["points"][0]["y"]

    def toggle(current, value):
        current = list(current or [])
        if value in current:
            current.remove(value)
        else:
            current.append(value)
        return current

    if source == "area-chart":
        return toggle(selected_areas, label), no_update, None, None
    return no_update, toggle(selected_crimes, label), None, None



if __name__ == "__main__":
    app.run(debug=True)