# -*- coding: utf-8 -*-
"""
Provider for Tags plugin.

License: BSD

(c) 2007 ::: www.CodeResort.com - BV Network AS (simon-code@bvnetwork.no)
"""

from tractags.api import TaggingSystem, ITaggingSystemProvider
tags_installed = True
from trac.core import *
from trac.util.compat import set
from trac.util.text import to_unicode
from model import BlogPost, get_blog_posts, get_months_authors_categories, \
        _parse_categories


class FullBlogTaggingSystem(TaggingSystem):
    """ An implementation of a tagging system. """

    def __init__(self, env):
        self.env = env

    def walk_tagged_names(self, names, tags, predicate):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        tags = set([to_unicode(tag) for tag in tags])
        names = set([to_unicode(name) for name in names])
        args = []
        sql = "SELECT name, categories FROM fullblog_posts "
        constraints = []
        if names:
            constraints.append("name IN (" + ', '.join(['%s' for n in names]) + ")")
            args += [to_unicode(n) for n in names]
        if tags:
            constraints.append("(" + ' OR '.join(["categories LIKE %s" for t in tags]) + ")")
            args += ['%' + t + '%' for t in tags]
        if constraints:
            sql += " WHERE " + " AND ".join(constraints)
        sql += " ORDER BY name"
        cursor.execute(sql, args)
        for row in cursor:
            post_name, categories = row[0], set(_parse_categories(row[1]))
            if not tags or categories.intersection(tags):
                if predicate(post_name, categories):
                    yield (post_name, categories)
            
    def get_name_tags(self, name):
        return get_months_authors_categories(self.env)[2]

    def add_tags(self, req, name, tags):
        pass

    def replace_tags(self, req, name, tags):
        pass

    def remove_tags(self, req, name, tags):
        pass

    def remove_all_tags(self, req, name):
        pass

    def name_details(self, name):
        bp = BlogPost(self.env, name)
        href = self.env.href.blog(name)
        return (href, '<a href="%s">Blog post: %s</a>' % (href, name),
            bp.title)

class FullBlogTagsProvider(Component):

    implements(ITaggingSystemProvider)

    def get_tagspaces_provided(self):
        """ Iterable of tagspaces provided by this tag system. """
        yield 'blog'

    def get_tagging_system(self, tagspace):
        return FullBlogTaggingSystem(self.env)
