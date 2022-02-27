import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

import bs4
import pandas as pd
from requests import get
from sqlalchemy import func

from models import provide_session, Refund

BASE_URL = 'https://www.gov.pl'
ANNOUNCEMENTS_BASE_URL = BASE_URL + '/web/zdrowie/obwieszczenia-ministra-zdrowia-lista-lekow-refundowanych'

LEGAL_FORMS = ('tabletki', 'tabletki powlekane', 'tabletki o przedłużonym uwalnianiu', 'kapsułki twarde', 'czopki')
VERBOSE_FORM_TO_CONCISE = {
    'kapsułki twarde': 'tabletki',
    'tabletki powlekane': 'tabletki',
    'tabletki o przedłużonym uwalnianiu': 'tabletki',
}


def parse_paginated_announcements(url, last_announcement_date=None):
    response = get(url)
    soup = bs4.BeautifulSoup(response.text, 'html.parser')

    for announcement in soup.find('div', class_='art-prev art-prev--near-menu')('a'):
        if 'Obwieszczenie' in announcement.find(class_='title').string and announcement.span:
            announcement_date = datetime.strptime(announcement.span.string.strip(), '%d.%m.%Y').date()
            if last_announcement_date and announcement_date <= last_announcement_date:
                return
            parse_announcement(announcement, announcement_date)
    next_button = soup.find(id='js-pagination-page-next')
    if next_button:
        parse_paginated_announcements(ANNOUNCEMENTS_BASE_URL + next_button['href'], last_announcement_date)


def parse_announcement(announcement, announcement_date):
    response = get(BASE_URL + announcement['href'])
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    for download_link in soup('a', class_='file-download'):
        if (any(x.strip().lower() == 'załącznik do obwieszczenia' for x in download_link.strings)
                and any('xlsx' in x for x in download_link.strings)):
            attachment = get(BASE_URL + download_link['href'])
            parse_attachment(attachment.content, announcement_date)


def parse_archived_announcements():
    directory = 'archived_announcements'

    file_names = os.listdir(directory)

    for file_name in file_names:
        path = os.path.join(directory, file_name)

        announcement_date = file_name.split('.')[0]
        if is_there_already_that_date(announcement_date):
            continue

        parse_attachment(path, announcement_date)


@provide_session
def parse_attachment(file, announcement_date, session):
    data = pd.read_excel(file, header=2, usecols='B:E,O,P')
    data.drop_duplicates(inplace=True)
    # We keep drugs with only one active ingredient
    data.drop(data.index[data['Substancja czynna'].str.contains(r'\+')], inplace=True)
    data[['Nazwa', 'Postać', 'Dawka']] = extract_details(data['Nazwa  postać i dawka'])
    data.drop(data.index[~data['Postać'].isin(LEGAL_FORMS)], inplace=True)
    data['Dawka'] = data['Dawka'].map(normalize_units)
    data['description_label'] = data['Nazwa'] + ' ' + data['Postać'] + ' ' + data['Zawartość opakowania']
    data['Postać'].replace(VERBOSE_FORM_TO_CONCISE, inplace=True)
    data['Wysokość dopłaty świadczeniobiorcy'].replace(',', '.', regex=True, inplace=True)
    data['units'] = data['Zawartość opakowania'].str.extract(r'(\d+) (szt|tabl|kaps)').loc[:, 0]
    data['unit price'] = data['Wysokość dopłaty świadczeniobiorcy'].astype(float) / data['units'].astype(int)
    data['description_dropdown'] = data['Nazwa'] + ' ' + data['Postać'] + ' ' + data['Zawartość opakowania'] + data['Substancja czynna'] + " " + data['Dawka']
    data['description_list_item'] = data['Nazwa']
    session.add_all(Refund(announcement_date=announcement_date, active_ingredient=row[0], ean=row[1],
                           refund_level=row[2], form=row[3], dose=row[4], description_label=row[5], unit_price=row[6], description_dropdown=row[7], description_list_item=row[8])
                    for row in data[['Substancja czynna', 'Kod EAN lub inny kod odpowiadający kodowi EAN',
                                     'Poziom odpłatności', 'Postać', 'Dawka', 'description_label', 'unit price', 'description_dropdown', 'description_list_item']].values)
    session.commit()


def extract_details(details):
    return details \
        .str.replace('tabl\\.', 'tabletki') \
        .str.replace('tabletka', 'tabletki') \
        .str.replace('kaps\\.', 'kapsułki') \
        .str.replace('powl\\.', 'powlekane') \
        .str.replace('powlekana', 'powlekane') \
        .str.replace('przedł\\.', 'przedłużonym') \
        .str.replace('tabletkipowlekane', 'tabletki powlekane') \
        .str.extract(r'^\s*([^,]*),\s*([^\d]*),\s*([\d].*[^\s])\s*$')


# changes j.m. to IU
# properly reads 'mln'
# conversion 'g' to 'mg'
def normalize_units(dose_string):

    if not dose_string:
        raise ValueError

    units = {
        'g': (1000, 'mg'),
        'mg': (1, 'mg'),
        'µg': (Decimal('0.001'), 'mg'),
        'μg': (Decimal('0.001'), 'mg'),
        'j.m.': (1, 'IU'),
        'IU': (1, 'IU')
    }

    if ', ' in dose_string:
        return ', '.join(normalize_units(chunk) for chunk in dose_string.split(', '))

    number, *multiplier, unit = dose_string.split(' ')
    number = number.replace(',', '.')

    try:
        return str(Decimal(number) * (10**6 if multiplier else 1) * units[unit][0]) + ' ' + units[unit][1]
    except InvalidOperation:
        return dose_string


@provide_session
def get_last_announcement_date(session):
    return session.query(func.max(Refund.announcement_date)).scalar()


@provide_session
def is_there_already_that_date(given_date, session):
    return session.query(Refund.announcement_date).filter_by(announcement_date=given_date).count() > 0


if __name__ == '__main__':
    parse_paginated_announcements(ANNOUNCEMENTS_BASE_URL, get_last_announcement_date())
    parse_archived_announcements()
