# -*- coding: utf-8 -*- #
# vim: ts=4 sw=4 tw=100 et ai si

AUTHOR = "Artem Bityutskiy"
SITENAME = "Wult"
SITEURL = "http://localhost:8000"

PATH = "content"
TIMEZONE = "UTC"
DEFAULT_LANG = "en"

DELETE_OUTPUT_DIRECTORY = True

DISPLAY_CATEGORIES_ON_MENU = False
DISPLAY_PAGES_ON_MENU = False
DISPLAY_ARTICLE_INFO_ON_INDEX=False
HIDE_SIDEBAR=True
HIDE_CATEGORIES=True

FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

DEFAULT_PAGINATION = False
#RELATIVE_URLS = True

PLUGIN_PATHS = ['../pelican-plugins']
PLUGINS = ['i18n_subsites', ]
JINJA_ENVIRONMENT = {
    'extensions': ['jinja2.ext.i18n'],
}

#THEME = "../pelican-fresh"
#THEME = "../pelican-themes/sneakyidea"
#THEME = "../pelican-themes/relapse"
THEME = "../pelican-themes/Peli-Kiera"
#THEME = "../pelican-themes/pelican-fh5co-marble"

#THEME = "../pelican-themes/pelican-bootstrap3"
#CC_LICENSE = "CC-BY"
#BOOTSTRAP_THEME = "flatly"
#BOOTSTRAP_THEME = "sandstone"
#BOOTSTRAP_THEME = "cerulean"
#BOOTSTRAP_THEME = "readable-old"
#PYGMENTS_STYLE = "vim"

STATIC_PATHS = ["results", "images"]
ARTICLE_EXCLUDES = ["results"]

MENUITEMS = (
    ("How it works", "/pages/how-it-works.html"),
    ("Install", "/pages/install-guide.html"),
    ("Use", "/pages/user-guide.html"),
    ("Howto", "/pages/howto.html"),
    ("Ndl", "/pages/ndl.html"),
)