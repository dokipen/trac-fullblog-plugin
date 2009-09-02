# -*- coding: utf-8 -*-
"""
Trac plugin proving a full-featured, self-contained Blog.

License: BSD

(c) 2007 ::: www.CodeResort.com - BV Network AS (simon-code@bvnetwork.no)
"""

from setuptools import setup

setup(name='TracFullBlogPlugin',
      version='0.1.1',
      packages=['tracfullblog'],
      author='CodeResort.com = BV Network AS',
      author_email='simon-code@bvnetwork.no',
      keywords='trac blog',
      description='Full-featured and self-contained Blog plugin for Trac.',
      url='http://trac-hacks.org/wiki/FullBlogPlugin',
      license='BSD',
      zip_safe = False,
      extras_require={
            'tags': 'TracTags>=0.6',
            'spamfilter': 'TracSpamFilter>=0.2'},
      entry_points={'trac.plugins': [
            'tracfullblog.admin = tracfullblog.admin',
            'tracfullblog.core = tracfullblog.core',
            'tracfullblog.db = tracfullblog.db',
            'tracfullblog.macros = tracfullblog.macros',
            'tracfullblog.spamfilter = tracfullblog.spamfilter[spamfilter]',
            'tracfullblog.tags = tracfullblog.tags[tags]',
            'tracfullblog.web_ui = tracfullblog.web_ui']},
      package_data={'tracfullblog' : ['htdocs/*.png',
                                      'htdocs/css/*.css',
                                      'htdocs/js/*.js',
                                      'templates/*.html',
                                      'templates/*.rss', ]},
      install_requires = [])
