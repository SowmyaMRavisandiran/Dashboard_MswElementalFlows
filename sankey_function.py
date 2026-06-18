import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go

def get_sector(df):
    df['sector'] = np.where(df['sector'].str.contains('OTH'), 'mix', 'source-separated')


#%% Colours
FRACTION_COLOURS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
]
TECH_COLOURS = [
    "#9c755f", "#bab0ac", "#499894", "#86bcb6",
    "#f1ce63", "#d4a6c8", "#86b7e4",
]

SECTOR_COLOURS = ["#2d6a4f", "#d4a017"]

#make link colours semi-transparent and convert from hex to rgb format
def hex_to_rgba(hex_col, alpha=0.4):
    hex_col = hex_col.lstrip("#")
    r, g, b = int(hex_col[0:2], 16), int(hex_col[2:4], 16), int(hex_col[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

#Generate node colours and link them to node names for sectors, fractions, and technologies
def get_node_colours(fractions_present, techs_present, sectors_present, sector_mode="within"):
    

    #Map the pre-defined colours to node names

    frac_colour    = {f: FRACTION_COLOURS[i % len(FRACTION_COLOURS)] for i, f in enumerate(fractions_present)}
    tech_colour    = {t: TECH_COLOURS[i % len(TECH_COLOURS)]         for i, t in enumerate(techs_present)}
    sector_colour  = {s: SECTOR_COLOURS[i % len(SECTOR_COLOURS)]     for i, s in enumerate(sectors_present)}

    node_colours = []

    #Get node colours based on mode of visualization for the sectors
    if sector_mode == "within":
        # (frac × sector) nodes with opacity
        for f in fractions_present:
            for s in sectors_present:
                alpha = 0.9 if s == "source-separated" else 0.4
                node_colours.append(hex_to_rgba(frac_colour[f], alpha=alpha))
    else:
        # sector_mode == 'separate'
        # left: fraction nodes, middle: sector nodes
        node_colours += [frac_colour[f]   for f in fractions_present]
        node_colours += [sector_colour[s] for s in sectors_present]

    node_colours += [tech_colour[t] for t in techs_present]
    return node_colours, frac_colour, tech_colour, sector_colour


#%% Mass calculation, label and create links functions

#%%%Conversion of units % wet weight and mg/kg to mass of element in tonnes
def to_mass(row, stat='Median'):
        amt  = row["technology amounts"]  # MT waste
        comp = row[stat]
        unit = str(row["Unit"]).lower()
        if "%" in unit:
            # comp is % wet weight  →  fraction = comp/100
            return amt * (comp / 100.0) *1e6         # element mass in tonnes
        elif "J" in unit:
            # comp is MJ/kg 
            return amt * (comp) *1e6         # LHV/HHV in GJ
        else:
            #comp is mg/kg = comp kg/1e6 kg
            #amt in Mt = amt * 1e9 kg
            #amt* comp = amt * 1e9 kg * comp kg/1e6 kg = amt * comp * 1e3 kg = amt * comp tonnes
            return amt * comp      # element mass in tonnes, comp in mg/kg
        
#%%%This function creates the labels and indices for fractions, sectors and technology nodes for each sector visualization mode

def get_labels(fractions_present, techs_present, sectors_present, sector_mode="within"):
    if sector_mode == "within":
        # left: (frac × sector), right: tech

        #left nodes are tuples of fraction, sector
        left_pairs     = [(f, s) for f in fractions_present for s in sectors_present]
        left_labels    = [f"{f} — {s}" for f, s in left_pairs]
        frac_sec_index = {(f, s): i for i, (f, s) in enumerate(left_pairs)}

        #right nodes are technologies
        tech_index     = {t: len(left_pairs) + i for i, t in enumerate(techs_present)}
        all_labels     = left_labels + list(techs_present)
        return all_labels, frac_sec_index, tech_index, None, None

    else:  # "separate" — left: fraction, middle: sector, right: tech
        frac_labels    = list(fractions_present)
        sector_labels  = list(sectors_present)
        tech_labels    = list(techs_present)

        n_frac   = len(fractions_present)
        n_sector = len(sectors_present)

        frac_index   = {f: i                    for i, f in enumerate(fractions_present)}
        sector_index = {s: n_frac + i           for i, s in enumerate(sectors_present)}
        tech_index   = {t: n_frac + n_sector + i for i, t in enumerate(techs_present)}

        all_labels = frac_labels + sector_labels + tech_labels
        return all_labels, None, tech_index, frac_index, sector_index

#%%% This function creates the links between source and target nodes
def create_links(fractions_present, techs_present, sectors_present, sub,
                 frac_sec_index, tech_index, frac_index, sector_index, value_mode, sector_mode="separate"):
    
    sources, targets, values, link_meta = [], [], [], []
    
    grouped = sub.groupby(["Fraction", "sector", "technology"])["elem_mass"].sum()
        
    if sector_mode == "within":
        # in this mode, sector is not a separate node, it is shown within the fraction node in the Sankey
        for frac in fractions_present:
            for sector in sectors_present:
                for tech in techs_present:
                    mass = grouped.get((frac, sector, tech), 0)
                    if mass <= 0:
                        continue
                    sources.append(frac_sec_index[(frac, sector)])
                    targets.append(tech_index[tech])
                    values.append(mass)
                    link_meta.append((frac, sector, tech))

    else:  # "separate"
        # Edge 1: fraction → sector
        grouped_fs = sub.groupby(["Fraction", "sector"])["elem_mass"].sum()
        for frac in fractions_present:
    
            for sector in sectors_present:
                mass = grouped_fs.get((frac, sector), 0)
                
                if mass <= 0:
                    continue
                sources.append(frac_index[frac])
                targets.append(sector_index[sector])
                values.append(mass)
                link_meta.append((frac, sector, None))

        # Edge 2: sector → technology
        for frac in fractions_present:
            for sector in sectors_present:
                for tech in techs_present:
                    mass = grouped.get((frac, sector, tech), 0)
                    if mass <= 0:
                        continue
                    sources.append(sector_index[sector])
                    targets.append(tech_index[tech])
                    values.append(mass)
                    link_meta.append((frac, sector, tech))

    if not values:
        return None, None, None, None, None

    if value_mode == "pct":
        total  = sum(values) or 1
        values = [v / total * 100 for v in values]
        value_label = "% element"
    else:
        value_label = "tonnes element"

    return sources, targets, values, value_label, link_meta

#%% Function to build sankey for one year, one element

def build_sankey(
    df: pd.DataFrame, # elemental composition and waste fraction generation and treatment data, filtered to a single country and scenario
    element: str, #build sankey for a single element
    year: int, #build sankey for a single year
    country: str,
    scenario: str = 'counterfactual',
    stat: str = 'Median',           # "Min" | "Median" | "Max"
    value_mode: str = 'mass',     # "mass" | "pct"
    sector_mode:str='separate',  #"within" | "separate"
) -> go.Figure:
    """
    Node layout
    ───────────
    Left column  : one node per (Fraction × source) labelled as "Frac – Generation → sector", where sector can be 'other' or 'source-separated'
    Right column : one node per (Fraction × Technology) labelled "Frac → Tech"

    Link values
    ───────────
    mass : technology_amounts [Mt] × elemental composition [stat]
           unit conversion: if Unit contains "%" divide by 100 and multiply by
           1e6 (to get element mass in tonnes); if "mg/kg" no changes (already total in tonnes).
    pct  : normalise each link so all links sum to 100 %.
    """
    sub = df[df["year"] == year].copy()
    if sub.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data for selection", showarrow=False,
                           font=dict(size=18))
        return fig

    # Compute element mass per link (tonnes of element)
    
    sub["elem_mass"] = sub[f"elem_mass_{stat}"]    # instant column lookup, no computation

    # ── build node lists ─────────────────────────────────────────────────
    fractions_present = sorted(sub["Fraction"].unique())

    techs_present     = sorted(sub["technology"].unique())
    sectors_present = sorted(sub["sector"].unique())
    
    all_labels, frac_sec_index, tech_index, frac_index, sector_index = get_labels(fractions_present, techs_present, sectors_present, sector_mode=sector_mode)

    # ── build links ──────────────────────────────────────────────────────
    sources, targets, values, value_label, link_meta = create_links(fractions_present, techs_present, sectors_present, sub, frac_sec_index, tech_index,frac_index,  sector_index, value_mode, sector_mode)
   
    # ── colours ──────────────────────────────────────────────────────────
    
    node_colours, frac_colour, tech_colour, sector_colour = get_node_colours(fractions_present, techs_present, sectors_present, sector_mode=sector_mode)
    
    link_colours = [hex_to_rgba(frac_colour.get(frac, "#aaaaaa"))
                    for frac, sector, tech in link_meta]

    hover_text = [
    f"{frac} ({sector}) → {tech}<br>{v:.4g} {value_label}"
    for (frac, sector, tech), v in zip(link_meta, values)
]
    
    # ── create figure ──────────────────────────────────────────────────────────
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20,
            thickness=20,
            line=dict(color="white", width=0.5),
            label=all_labels,
            color=node_colours,
            hovertemplate="%{label}<br>Total: %{value:.4g} " + value_label + "<extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colours,
            customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>",
        ),
    ))

    unit_str  = sub["Unit"].iloc[0] if not sub.empty else ""
    mode_str  = "Percentage of total flow (%)" if value_mode == "pct" \
                else f"Element mass ({value_label})"

    fig.update_layout(
        title=dict(
            text=(
                f"<b>Element flow: {element}</b>  |  "
                f"Year {year}  |  {stat} composition  |  {mode_str}<br>"
                f"<sup>Composition unit: {unit_str}</sup>"
            ),
            font=dict(size=15),
        ),
        font=dict(size=12, family="Arial"),
        paper_bgcolor="#f9f9f9",
        plot_bgcolor="#f9f9f9",
        height=650,
        margin=dict(l=20, r=20, t=90, b=20),
    )
    return fig

#%% Functions for building animated sankey

#%%% this uses generates the links created for each year
def get_links_for_year(yr, df, fractions_present, techs_present, sectors_present,
                       frac_sec_index, tech_index,frac_index, sector_index,
                       frac_colour, element, stat, value_mode, sector_mode="separate"):
    
    sub = df[(df["Element"] == element) & (df["year"] == int(yr))].copy()

    sub["elem_mass"] = sub[f"elem_mass_{stat}"]    # instant column lookup, no computation

    sources, targets, values, value_label, link_meta = create_links(
        fractions_present, techs_present, sectors_present, sub,
        frac_sec_index, tech_index,frac_index, sector_index, value_mode, sector_mode  # ← pass through
    )
    link_colours = [
        hex_to_rgba(frac_colour.get(frac, "#aaaaaa"))
        for frac, sector, tech in link_meta
    ]
    hover_text = [
    f"{frac} ({sector}) → {tech}<br>{v:.4g} {value_label}"
    for (frac, sector, tech), v in zip(link_meta, values)]
    return sources, targets, values, link_colours, hover_text

#%%% ANIMATED HTML BUILDER  (all years as slider frames)

def build_animated_sankey(
    df: pd.DataFrame,
    element: str,
    country: str = 'AUST',
    scenario: str = 'counterfactual',
    stat: str = "Median",
    value_mode: str = "mass",
) -> go.Figure:
    """
    Returns a figure with a year-slider (Plotly animation frames).
    Each frame is a full Sankey for that year.
    Saved as self-contained HTML.
    """
    years_sorted = sorted(df["year"].unique())

    df_sub = df[
        (df["Element"]  == element) &
        (df["country"]  == country) &
        (df["scenario"] == scenario)
    ]
 
    # Get labels of sankey nodes: Build a consistent node list across ALL years so indices stay stable
    fractions_present = sorted(df_sub["Fraction"].unique())
    techs_present     = sorted(df_sub["technology"].unique())
    sectors_present = sorted(df_sub["sector"].unique())
 

    all_labels, frac_sec_index, tech_index, frac_index, sector_index  = get_labels(fractions_present, techs_present, sectors_present, sector_mode='separate')

    #Get colours
    node_colours, frac_colour, tech_colour, sector_colour = get_node_colours( # ← updated signature
        fractions_present, techs_present, sectors_present, sector_mode='separate' )
    
    value_label = "%" if value_mode == "pct" else "MT element"
 
    # First frame

    s0, t0, v0, lc0, hover_text = get_links_for_year(years_sorted[0], df, fractions_present, techs_present,sectors_present,frac_sec_index, tech_index, frac_index, sector_index, frac_colour, element, stat, value_mode, sector_mode='separate')
 
    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(
                pad=20, thickness=20,
                line=dict(color="white", width=0.5),
                label=all_labels,
                color=node_colours,
            ),
            link=dict(source=s0, target=t0, value=v0, color=lc0, customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>"),
        )
    )
 
    # Animation frames
    frames = []
    for yr in years_sorted:
       
        s, t, v, lc, hover_text = get_links_for_year(yr, df, fractions_present, techs_present, sectors_present, frac_sec_index, tech_index, frac_index, sector_index, frac_colour, element, stat, value_mode, sector_mode='separate')
        frames.append(go.Frame(
            data=[go.Sankey(
                arrangement="snap",
                node=dict(
                    pad=20, thickness=20,
                    line=dict(color="white", width=0.5),
                    label=all_labels,
                    color=node_colours,
                ),
                link=dict(source=s, target=t, value=v, color=lc, customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>"),
            )],
            name=str(int(yr)),
        ))
    fig.frames = frames
 
    # Slider steps
    sliders = [dict(
        active=0,
        currentvalue={"prefix": "Year: ", "font": {"size": 14}},
        pad={"t": 50},
        steps=[
            dict(
                label=str(int(yr)),
                method="animate",
                args=[[str(int(yr))], {"frame": {"duration": 500, "redraw": True},
                                       "mode": "immediate"}],
            )
            for yr in years_sorted
        ],
    )]
 
    fig.update_layout(
        title=dict(
            text=(
                f"<b>Element flow: {element}</b>  |  "
                f"{stat} composition  |  "
                f"{'Percentage (%)' if value_mode == 'pct' else 'Element mass (MT)'}"
            ),
            font=dict(size=15),
        ),
        updatemenus=[dict(
            type="buttons", showactive=False,
            y=1.15, x=0.5, xanchor="center",
            buttons=[
                dict(label="▶ Play",
                     method="animate",
                     args=[None, {"frame": {"duration": 800, "redraw": True},
                                  "fromcurrent": True}]),
                dict(label="⏸ Pause",
                     method="animate",
                     args=[[None], {"frame": {"duration": 0}, "mode": "immediate"}]),
            ],
        )],
        sliders=sliders,
        font=dict(size=12, family="Arial"),
        paper_bgcolor="#f9f9f9",
        height=700,
        margin=dict(l=20, r=20, t=110, b=20),
    )
    return fig

#%% Save figures

def save_figures(
    out_dir: str = "sankey_output/version",
    country:str = None,
    scenario:str='counterfactual',
    stat: str = "Median",
    png_year: int = None,       # which year for the static PNG (defaults to first year)
    value_mode: str = "mass",   # "mass" or "pct"
    version:int = 1, #version for figure names
):
    """
    For every element:
      - saves one PNG  (static, single year = png_year)
      - saves one HTML (interactive slider across all years)
 
    Requirements:
      PNG  → pip install kaleido
      HTML → no extra packages needed
    """
    out_dir=f"{out_dir}_v{version}"
    os.makedirs(out_dir, exist_ok=True)
    elements_list = df["Element"].dropna().unique()
    year_for_png  = int(png_year) if png_year is not None \
                    else int(sorted(df["year"].unique())[0])
 
    for elem in elements_list:
        print(f"Saving {elem}...")
 
        # ── PNG (static, one year) ──────────────────────────────────────
        fig_png = build_sankey(df, element=elem, year=year_for_png,country=country, 
                               scenario=scenario,
                               stat=stat, value_mode=value_mode)
        png_path = os.path.join(out_dir, f"sankey_{elem}_{year_for_png}_v{version}.png")
        fig_png.write_image(png_path, width=1400, height=700, scale=2)
        print(f"  PNG  → {png_path}")
 
        # ── HTML (animated, all years) ──────────────────────────────────
        fig_html = build_animated_sankey(df, element=elem,
                                         stat=stat, value_mode=value_mode)
        html_path = os.path.join(out_dir, f"sankey_{elem}_animated.html")
        fig_html.write_html(html_path, include_plotlyjs="cdn")
        print(f"  HTML → {html_path}")
 
    print(f"\nDone. All files saved to '{out_dir}/'")
 