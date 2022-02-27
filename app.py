from datetime import date, timedelta
from itertools import groupby

import dash
import dash_core_components as dcc
import dash_html_components as html
import flask
import pdfkit
from dash.dependencies import Input, Output
from sqlalchemy import func, tuple_

from models import provide_session, Refund

# this path does not make app use this url,
# it only informs app that it uses it
base_url = f'http://localhost:8050'

def get_marker(label_index, size=15, line_width=2):
    # codes taken from https://plotly.com/python/marker-style/
    our_symbols = [37, 38, 39, 40]

    # I think those are used in plotly by default
    # to choose label colors, but it did't work
    # so I took control over it
    our_colors = ['rgb(31, 119, 180)', 'rgb(255, 127, 14)',
                  'rgb(44, 160, 44)', 'rgb(214, 39, 40)',
                  'rgb(148, 103, 189)', 'rgb(140, 86, 75)',
                  'rgb(227, 119, 194)', 'rgb(127, 127, 127)',
                  'rgb(188, 189, 34)', 'rgb(23, 190, 207)']

    def chose(l, i):
        return l[i % len(l)]

    return {
        'line': {'color': chose(our_colors, label_index), 'width': line_width},
        'size': size,
        'symbol': chose(our_symbols, label_index)
    }


external_scripts = ['https://cdn.plot.ly/plotly-locale-pl-latest.js']
external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

server = flask.Flask(__name__)


@server.route('/')
def index():
    return flask.redirect('/dash')


@server.route('/pdf/<ean>/')
def render_pdf(ean):
    pdf = pdfkit.from_url(
        base_url + f'/dash/{ean}/', False, options={'javascript-delay': '5000'
                                                              })
    response = flask.make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={ean}.pdf'
    return response


@provide_session
def get_dropdown_items(session):
    return session.query(Refund.ean, Refund.description_dropdown).order_by(Refund.ean).distinct()


app = dash.Dash(__name__, server=server, routes_pathname_prefix='/dash/', external_scripts=external_scripts,
                external_stylesheets=external_stylesheets)
app.layout = html.Div( style={'backgroundColor':'white'}, children=[
    dcc.Location(id='url', refresh=False),
    dcc.Dropdown(
        id='dropdown',
        options=[{'label': '%s (%s)' % (ean, description), 'value': ean} for ean, description in get_dropdown_items()]),

    html.Div(id='content', children=[]),
    html.A(id='pdf', children='Zapisz jako PDF', hidden=True)])


@app.callback(Output('dropdown', 'value'), [Input('url', 'pathname')], prevent_initial_call=True)
def load_ean(pathname):
    ean = pathname.split('/')[2]
    if not ean:
        raise dash.exceptions.PreventUpdate
    return ean


def calculate_plot_height_avoiding_scroll(max_num_of_labels):
    base_height = 600
    height_per_label = 30

    num_fitting_in_base_height = base_height // height_per_label
    result = base_height
    if (max_num_of_labels > num_fitting_in_base_height):
        result += height_per_label * \
            (max_num_of_labels - num_fitting_in_base_height)

    return result

def sort_both_arrays_based_on_first_array(keys, values):
    indices = [i for i in range(len(keys))]
    def key_fun(i):
        return keys[i]
    order = sorted(indices, key=key_fun)
    out_keys = [keys[i] for i in order]
    out_values = [values[i] for i in order]
    return out_keys, out_values


@app.callback([Output('content', 'children'), Output('pdf', 'hidden'), Output('pdf', 'href')],
              [Input('dropdown', 'value')], prevent_initial_call=True)
@provide_session
def get_graphs(ean, session):
    subquery = session.query(
        Refund.active_ingredient, Refund.dose, Refund.form).filter_by(ean=ean).distinct()
    records = session.query(Refund.refund_level, Refund.description_label,
                            func.array_agg(Refund.announcement_date).label(
                                'announcement_dates'),
                            func.array_agg(Refund.unit_price).label('unit_prices'), Refund.description_list_item). \
        filter(tuple_(Refund.active_ingredient, Refund.dose, Refund.form).in_(subquery)). \
        group_by(Refund.refund_level, Refund.description_label, Refund.description_list_item). \
        order_by(Refund.refund_level)

    def get_grouped():
        return groupby(records, key=lambda record: record.refund_level)

    max_labels_number_in_plot = max([
        len(list(drugs))
        for _, drugs in get_grouped()
    ])

    children_to_return = []

    for refund_level, drugs in get_grouped():
        list_children = []
        data_graph = []

        for index, drug in enumerate(sorted(filtered(drugs), key=drug_comparision_key, reverse=True)):
            x, y = sort_both_arrays_based_on_first_array(drug['announcement_dates'], drug['unit_prices'])
            data_graph.append(dict(
                        x=x,
                        y=y,
                        name="{}. {}".format(
                            str(index + 1), drug['description_list_item']),
                        mode='lines+markers',
                        marker=get_marker(index),
                        hoverinfo='text',
                        text=["{}. {} zł".format(str(index + 1), str(a))
                              for a in drug['unit_prices']],
                        visible=True if index < 3 else "legendonly"
                    ))

            list_children.append(
                html.Li("{}. {}".format(index + 1, drug['description_label']))
            )
        children_to_return.append(
            html.Ul(children=list_children)
        )

        children_to_return.append(
            dcc.Graph(figure=dict(
                data=data_graph,
                layout=dict(
                    title=refund_level,
                    showlegend=True,
                    yaxis=dict(title='Cena za jednostkę leku [zł]',
                               automargin=True,
                               rangemode='tozero'
                               ),
                    height=calculate_plot_height_avoiding_scroll(
                        max_labels_number_in_plot)
                )
            ))
        )

    return children_to_return, False, base_url + f'/pdf/{ean}/'


def filtered(drugs):
    return [{
        'description_label': drug.description_label,
        'description_list_item': drug.description_list_item,
        'unit_prices': [unit_price for i, unit_price in enumerate(drug.unit_prices)
                        if drug.announcement_dates[i] >= date.today() - timedelta(days=3*365)],
        'announcement_dates': [announcement_date for announcement_date in drug.announcement_dates
                               if announcement_date >= date.today() - timedelta(days=3 * 365)]
    } for drug in drugs]


def drug_comparision_key(drug):
    last_announcement_date = max(drug['announcement_dates'])
    return last_announcement_date, -drug['unit_prices'][drug['announcement_dates'].index(last_announcement_date)]


if __name__ == '__main__':
    app.run_server()
