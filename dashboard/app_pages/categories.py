import streamlit as st

from dashboard.ui import brl, cached, card, filters, header, kpi, pal, pct, plot, px, window_badges

start, end, state = filters()
header("Category performance", ":material/category:",
       "Olist product categories stand in for restaurant or cuisine categories. They are not equivalent.",
       window_badges(start, end, state))

cp = cached("category_performance", start, end, state)
sc = cached("seller_concentration")
with st.container(horizontal=True):
    kpi("Categories with sales", f"{len(cp)}", icon=":material/category:")
    kpi("Top-10 category GMV share", pct(cp.gmv_share.head(10).sum()),
              icon=":material/leaderboard:")
    kpi("Leading category", cp.category.iloc[0].replace("_", " "), icon=":material/star:",
              help=f"{brl(cp.gmv.iloc[0])} GMV, {pct(cp.gmv_share.iloc[0])} share")
    kpi("Top 10% sellers' GMV share", pct(sc["top10pct_share"]), icon=":material/storefront:",
              help=f"Full window. {int(sc['sellers']):,} sellers; HHI {sc['hhi']:.0f}.")

left, right = st.columns(2)
with left:
    with card("GMV by category", ":material/bar_chart:"):
        top_n = st.slider("Categories shown", 5, 30, 12)
        top = cp.head(top_n).assign(label=lambda d: d.category.str.replace("_", " "))
        fig = px.bar(top, y="label", x="gmv", orientation="h", labels={"label": "", "gmv": "GMV (BRL)"},
                     hover_data={"gmv_share": ":.1%", "orders": ":,", "avg_item_price": ":.2f", "label": False})
        fig.update_yaxes(autorange="reversed")
        plot(fig, alt="GMV by product category", legend=False, height=420, hover="y unified")
with right:
    with card("Quality map", ":material/scatter_plot:",
              "Categories with at least 1% GMV share; bubble size is GMV. Association only: product size and seller "
              "location confound this."):
        mat = cp[cp.gmv_share >= 0.01].assign(label=lambda d: d.category.str.replace("_", " "))
        fig = px.scatter(mat, x="on_time_rate", y="avg_review", size="gmv", hover_name="label",
                         labels={"on_time_rate": "On-time rate", "avg_review": "Avg review"},
                         hover_data={"gmv": ":,.0f", "share_1_2_star": ":.1%"}, size_max=38)
        fig.update_traces(marker=dict(color=pal()["series"][0], opacity=0.8, line=dict(color=pal()["mark_gap"], width=1.5)))
        worst = mat.nsmallest(3, "avg_review")
        for _, r in worst.iterrows():
            fig.add_annotation(x=r.on_time_rate, y=r.avg_review, text=r.label, showarrow=False, yshift=-16,
                               font=dict(size=11, color=pal()["ink2"]))
        fig.update_xaxes(tickformat=".0%")
        plot(fig, alt="Category on-time rate versus average review", legend=False, height=470, hover="closest")

with card("Monthly GMV by category", ":material/timeline:"):
    cats = st.multiselect("Categories", cached("categories"), default=cached("categories")[:3], max_selections=8)
    cm = cached("category_monthly", tuple(cats), start, end)
    fig = px.line(cm, x="month", y="gmv", color="category", markers=True, labels={"gmv": "GMV (BRL)", "month": ""},
                  category_orders={"category": cats})
    plot(fig, alt="Monthly GMV for selected categories", height=320)

with card("Category scorecard", ":material/table_chart:"):
    st.dataframe(cp, hide_index=True, alt="Category scorecard", column_order=[
        "gmv_rank", "category", "gmv", "gmv_share", "orders", "avg_item_price", "sellers", "avg_review",
        "share_1_2_star", "on_time_rate", "avg_delivery_days"], column_config={
        "gmv_rank": st.column_config.NumberColumn("#"),
        "category": st.column_config.TextColumn("Category"),
        "gmv": st.column_config.NumberColumn("GMV (R$)", format="localized"),
        "gmv_share": st.column_config.ProgressColumn("GMV share", format="percent", min_value=0,
                                                     max_value=float(cp.gmv_share.max())),
        "orders": st.column_config.NumberColumn("Orders", format="localized"),
        "avg_item_price": st.column_config.NumberColumn("Avg price (R$)", format="%.2f"),
        "sellers": st.column_config.NumberColumn("Sellers"),
        "avg_review": st.column_config.NumberColumn("Avg review", format="%.2f ★"),
        "share_1_2_star": st.column_config.NumberColumn("1–2★ share", format="percent"),
        "on_time_rate": st.column_config.ProgressColumn("On-time", format="percent", min_value=0.8, max_value=1),
        "avg_delivery_days": st.column_config.NumberColumn("Delivery days", format="%.1f"),
    })
