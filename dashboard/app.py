from dash import Dash, html, dcc, Input, Output
import plotly.express as px

from dashboard.database import query_database


app = Dash(__name__)


# --------------------------------------------------
# LOAD FILTER OPTIONS FROM DATABASE
# --------------------------------------------------

years = query_database("""
    SELECT DISTINCT year
    FROM crime_incidents
    ORDER BY year;
""")["year"].tolist()


months = query_database("""
    SELECT DISTINCT EXTRACT(MONTH FROM date_occ)::INTEGER AS month_number,
           TO_CHAR(date_occ, 'Month') AS month_name
    FROM crime_incidents
    ORDER BY month_number;
""")


areas = query_database("""
    SELECT DISTINCT area_name
    FROM crime_incidents
    ORDER BY area_name;
""")["area_name"].tolist()


crime_types = query_database("""
    SELECT DISTINCT crime_description
    FROM crime_incidents
    ORDER BY crime_description;
""")["crime_description"].tolist()


# --------------------------------------------------
# APP LAYOUT
# --------------------------------------------------

app.layout = html.Div(
    [

        html.H1(
            "Los Angeles Crime Analytics",
            style={"textAlign": "center"}
        ),

        html.P(
            "LAPD reported crime records, 2020–2024",
            style={"textAlign": "center"}
        ),

        html.Hr(),

        # ---------------- FILTERS ----------------

        html.H2("Filters"),

        html.Div(
            [

                # YEAR
                html.Div(
                    [
                        html.Label("Year"),

                        dcc.Dropdown(
                            id="year-filter",
                            options=[
                                {"label": str(year), "value": year}
                                for year in years
                            ],
                            multi=True,
                            placeholder="All Years"
                        )
                    ],
                    style={
                        "width": "23%",
                        "display": "inline-block",
                        "marginRight": "1%"
                    }
                ),

                # MONTH
                html.Div(
                    [
                        html.Label("Month"),

                        dcc.Dropdown(
                            id="month-filter",
                            options=[
                                {
                                    "label": row["month_name"].strip(),
                                    "value": row["month_number"]
                                }
                                for _, row in months.iterrows()
                            ],
                            multi=True,
                            placeholder="All Months"
                        )
                    ],
                    style={
                        "width": "23%",
                        "display": "inline-block",
                        "marginRight": "1%"
                    }
                ),

                # AREA
                html.Div(
                    [
                        html.Label("LAPD Area"),

                        dcc.Dropdown(
                            id="area-filter",
                            options=[
                                {
                                    "label": area,
                                    "value": area
                                }
                                for area in areas
                            ],
                            multi=True,
                            placeholder="All Areas"
                        )
                    ],
                    style={
                        "width": "23%",
                        "display": "inline-block",
                        "marginRight": "1%"
                    }
                ),

                # CRIME TYPE
                html.Div(
                    [
                        html.Label("Crime Type"),

                        dcc.Dropdown(
                            id="crime-filter",
                            options=[
                                {
                                    "label": crime,
                                    "value": crime
                                }
                                for crime in crime_types
                            ],
                            multi=True,
                            placeholder="All Crime Types"
                        )
                    ],
                    style={
                        "width": "23%",
                        "display": "inline-block"
                    }
                ),

            ]
        ),

        html.Br(),

        html.Hr(),

        # ---------------- KPI CARDS ----------------

        html.Div(
            [

                html.Div(
                    [
                        html.H4("Total Incidents"),
                        html.H2(id="total-incidents")
                    ],
                    style={
                        "width": "30%",
                        "display": "inline-block",
                        "textAlign": "center"
                    }
                ),

                html.Div(
                    [
                        html.H4("Average Victim Age"),
                        html.H2(id="average-age")
                    ],
                    style={
                        "width": "30%",
                        "display": "inline-block",
                        "textAlign": "center"
                    }
                ),

                html.Div(
                    [
                        html.H4("Crime Types"),
                        html.H2(id="crime-type-count")
                    ],
                    style={
                        "width": "30%",
                        "display": "inline-block",
                        "textAlign": "center"
                    }
                ),

            ]
        ),

        html.Hr(),

        # ---------------- CHARTS ----------------

        dcc.Graph(id="year-chart"),

        dcc.Graph(id="area-chart"),

        dcc.Graph(id="crime-chart"),

    ],

    style={
        "maxWidth": "1400px",
        "margin": "auto",
        "padding": "20px"
    }
)


# --------------------------------------------------
# CALLBACK
# --------------------------------------------------

@app.callback(
    Output("total-incidents", "children"),
    Output("average-age", "children"),
    Output("crime-type-count", "children"),
    Output("year-chart", "figure"),
    Output("area-chart", "figure"),
    Output("crime-chart", "figure"),

    Input("year-filter", "value"),
    Input("month-filter", "value"),
    Input("area-filter", "value"),
    Input("crime-filter", "value"),
)


def update_dashboard(
    selected_years,
    selected_months,
    selected_areas,
    selected_crimes
):

    # ----------------------------------------------
    # BUILD SQL FILTER
    # ----------------------------------------------

    conditions = []
    params = {}

    # YEARS

    if selected_years:

        placeholders = []

        for i, year in enumerate(selected_years):

            key = f"year_{i}"

            placeholders.append(f":{key}")

            params[key] = year

        conditions.append(
            f"year IN ({', '.join(placeholders)})"
        )


    # MONTHS

    if selected_months:

        placeholders = []

        for i, month in enumerate(selected_months):

            key = f"month_{i}"

            placeholders.append(f":{key}")

            params[key] = month

        conditions.append(
            f"EXTRACT(MONTH FROM date_occ)::INTEGER "
            f"IN ({', '.join(placeholders)})"
        )


    # AREAS

    if selected_areas:

        placeholders = []

        for i, area in enumerate(selected_areas):

            key = f"area_{i}"

            placeholders.append(f":{key}")

            params[key] = area

        conditions.append(
            f"area_name IN ({', '.join(placeholders)})"
        )


    # CRIME TYPES

    if selected_crimes:

        placeholders = []

        for i, crime in enumerate(selected_crimes):

            key = f"crime_{i}"

            placeholders.append(f":{key}")

            params[key] = crime

        conditions.append(
            f"crime_description IN ({', '.join(placeholders)})"
        )


    # ----------------------------------------------
    # WHERE CLAUSE
    # ----------------------------------------------

    if conditions:

        where_clause = "WHERE " + " AND ".join(conditions)

    else:

        where_clause = ""


    # ----------------------------------------------
    # KPI QUERY
    # ----------------------------------------------

    kpi = query_database(
        f"""
        SELECT
            COUNT(*) AS total_incidents,
            ROUND(AVG(victim_age), 1) AS average_age,
            COUNT(DISTINCT crime_description) AS crime_types
        FROM crime_incidents
        {where_clause};
        """,
        params
    )

    total = int(kpi.iloc[0]["total_incidents"])

    average_age = kpi.iloc[0]["average_age"]

    if average_age is None:
        average_age_display = "N/A"
    else:
        average_age_display = f"{float(average_age):.1f}"

    crime_type_count = int(kpi.iloc[0]["crime_types"])


    # ----------------------------------------------
    # YEAR CHART
    # ----------------------------------------------

    yearly = query_database(
        f"""
        SELECT
            year,
            COUNT(*) AS incidents
        FROM crime_incidents
        {where_clause}
        GROUP BY year
        ORDER BY year;
        """,
        params
    )

    year_fig = px.line(
        yearly,
        x="year",
        y="incidents",
        markers=True,
        title="Reported Crime Over Time"
    )


    # ----------------------------------------------
    # AREA CHART
    # ----------------------------------------------

    area_data = query_database(
        f"""
        SELECT
            area_name,
            COUNT(*) AS incidents
        FROM crime_incidents
        {where_clause}
        GROUP BY area_name
        ORDER BY incidents DESC;
        """,
        params
    )

    area_fig = px.bar(
        area_data,
        x="area_name",
        y="incidents",
        title="Crime by LAPD Area"
    )


    # ----------------------------------------------
    # CRIME TYPE CHART
    # ----------------------------------------------

    crime_data = query_database(
        f"""
        SELECT
            crime_description,
            COUNT(*) AS incidents
        FROM crime_incidents
        {where_clause}
        GROUP BY crime_description
        ORDER BY incidents DESC
        LIMIT 15;
        """,
        params
    )

    crime_fig = px.bar(
        crime_data,
        x="incidents",
        y="crime_description",
        orientation="h",
        title="Top 15 Crime Types"
    )


    return (
        f"{total:,}",
        average_age_display,
        f"{crime_type_count:,}",
        year_fig,
        area_fig,
        crime_fig
    )


# --------------------------------------------------
# RUN APP
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)