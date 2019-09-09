from smtplib import SMTPAuthenticationError
from argparse import ArgumentParser
from bs4 import BeautifulSoup
from smtplib import SMTP_SSL
from io import StringIO
import requests
import pickle
import json
import sys
import re
import os

URL = 'https://cloudwaterbrew.co/unit9menu'
FILE_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
FILENAME = 'beer_list.pkl'
DATABASE_PATH = os.path.join(FILE_DIRECTORY, FILENAME)

SERVER_DETAILS = ('smtp.gmail.com', 465)
EMAIL_SUBJECT = 'Cloudwater Unit-9 updates!'
FROM = 'Unit-9 Notifier'


def load_details(keys=('username', 'password', 'recipient')):
    credentials_file_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'credentials.json'
    )
    with open(credentials_file_path) as fd:
        data = json.load(fd)

    return (data[key] for key in keys)


class Capture():
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = StringIO()

        return self

    def __exit__(self, *args):
        self.value = self._stringio.getvalue()
        sys.stdout = self._stdout
        print(self.value, end='')


class Beer():
    def __init__(self, name, desc, extra_info, strength):
        self.name = name
        self.desc = desc
        self.extra_info = extra_info
        self.strength = strength

    def __repr__(self):
        base_string = '{}\n\t"{}"\n\t{:.1f}%'.format(
            self.name, self.desc, self.strength
        )
        if self.extra_info is None:
            return base_string + '\n'

        return base_string + ' - ' + self.extra_info + '\n'


def write_db(beers):
    with open(DATABASE_PATH, 'wb') as fd:
        pickle.dump(beers, fd)


def read_db():
    with open(FILENAME, 'rb') as fd:
        beers = pickle.load(fd)

    return beers


def build_parser():
    parser = ArgumentParser(description=__doc__)

    parser.add_argument(
        '-e', '--email',
        action='store_true',
        default=False,
        help='Whether to email the results.'
    )

    parser.add_argument(
        '--no-save',
        action='store_true',
        default=False,
        help='Whether to not save results.'
    )

    return parser


def get_name(menu_item):
    title_div = menu_item.find(
        class_='menu-item-title'
    )

    title_text = title_div.text

    # A beer may or may not have an asterisk appended.
    title_text = title_text.replace('*', '')
    title_text = title_text.rstrip()

    return title_text


def get_description(menu_item):
    description_div = menu_item.find(
        class_='menu-item-description'
    )

    description = description_div.text

    return description


def get_extra_info(menu_item):
    extra_info = menu_item.find(
        class_='menu-item-option'
    )

    if extra_info:
        return extra_info.text


def get_strength(menu_item):
    strength_div = menu_item.find(class_='currency-sign').next
    strength = re.match(r'\d+\.?\d*', strength_div)[0]
    strength = float(strength)

    return strength


def parse_beer(menu_item):
    getter_functions = (
        get_name, get_description, get_extra_info, get_strength
    )

    name, *rest = (
        function(menu_item)
        for function in getter_functions
    )

    return name, Beer(name, *rest)


def get_menu_items():
    content = requests.get(URL).content
    decoded = content.decode('utf-8')
    content = decoded.replace(r'/br', 'br').encode('utf-8')

    soup = BeautifulSoup(content, 'html.parser')
    menu_items = soup.find_all(class_='menu-item')

    return menu_items


def get_beers():
    menu_items = get_menu_items()

    beers = dict(parse_beer(menu_item) for menu_item in menu_items)

    return beers


def check_difference(beers, other_beers, suffix='added'):
    differences = other_beers.keys() - beers.keys()
    if differences:
        print('Some beers were {}:'.format(suffix))
        for different_beer in differences:
            print(other_beers[different_beer])

        return True

    return False


def check_for_changes(beers):
    if os.path.isfile(FILENAME):
        previous_beers = read_db()

        some_removed = check_difference(beers, previous_beers, 'removed')
        some_added = check_difference(previous_beers, beers, 'added')
        return some_added or some_removed
    else:
        print('No previous record found! Beers are:')
        for beer in beers.values():
            print(beer)

        return True


def send_email(message, subject=EMAIL_SUBJECT, from_name=FROM):
    message = 'Subject: {}\nFrom: {}\n\n{}'.format(subject, from_name, message)
    message = message.encode('utf8')

    try:
        username, password, recipient = load_details()
    except FileNotFoundError:
        print('Could not find email credentials!')
        return False

    try:
        server = SMTP_SSL(*SERVER_DETAILS)
        server.ehlo()
        server.login(username, password)

        server.sendmail(username, recipient, message)

        server.close()
    except SMTPAuthenticationError as e:
        print(e)
        print('Authentication error, is the password correct?')
        print(
            'Are less secure apps allowed? '
            '(https://myaccount.google.com/lesssecureapps)'
        )
        return False

    return True


def main():
    args = build_parser().parse_args()

    beers = get_beers()

    with Capture() as output:
        has_changed = check_for_changes(beers)
    message = output.value

    if args.email:
        if len(message) == 0:
            print('No updates to email!')
        else:
            success = send_email(message)
            if success:
                print('Email sent.')
            else:
                print('Something went wrong with the email.')

    if args.no_save:
        return

    if has_changed:
        write_db(beers)
        print('Beer database written.')
    else:
        print('Nothing changed.')


if __name__ == '__main__':
    main()
