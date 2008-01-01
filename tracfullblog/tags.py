# -*- coding: utf-8 -*-
"""
Provider for Tags plugin.

License: BSD

(c) 2007 ::: www.CodeResort.com - BV Network AS (simon-code@bvnetwork.no)
"""

from trac.core import *
from tractags.api import ITagProvider
from trac.util.compat import set
from trac.util.text import to_unicode
from trac.resource import Resource
from model import BlogPost, _parse_categories


class FullBlogTagSystem(Component):
    implements(ITagProvider)

    # ITagProvider methods
    def get_taggable_realm(self):
        return 'blog'

    def get_tagged_resources(self, req, tags):
        if 'TAGS_VIEW' not in req.perm or 'BLOG_VIEW' not in req.perm:
            return

        db = self.env.get_db_cnx()
        cursor = db.cursor()

        args = []
        constraints = []
        sql = "SELECT name, categories FROM fullblog_posts"
        if tags:
            constraints.append("(" + ' OR '.join(["categories LIKE %s" for t in tags]) + ")")
            args += ['%' + t + '%' for t in tags]
        else:
            constraints.append("categories != ''")
        if constraints:
            sql += " WHERE " + " AND ".join(constraints)
        sql += " GROUP BY name ORDER BY name"
        self.env.log.debug(sql)
        cursor.execute(sql, args)
        for row in cursor:
            post_name, categories = row[0], set(_parse_categories(row[1]))
            if not tags or categories.intersection(tags):
                resource = Resource('blog', post_name)
                if 'BLOG_VIEW' in req.perm(resource) and \
                        'TAGS_VIEW' in req.perm(resource):
                    yield (resource, categories)

    def get_resource_tags(self, req, resource):
        req.perm(resource).require('BLOG_VIEW')
        req.perm(resource).require('TAGS_VIEW')
        return BlogPost(self.env, resource.id).category_list

    def set_resource_tags(self, req, resource, tags):
        req.perm(resource).require('TAGS_MODIFY')
        post = BlogPost(self.env, resource.id)
        if post.author == req.authname:
            req.perm(resource).require('BLOG_MODIFY_OWN')
        else:
            req.perm(resource).require('BLOG_MODIFY_ALL')
        post.categories = " ".join(tags)
        post.save(req.authname, 'Blog post categories changed via Tags plugin.')

    def remove_resource_tags(self, req, resource):
        req.perm(resource).require('TAGS_MODIFY')
        post = BlogPost(self.env, resource.id)
        if post.author == req.authname:
            req.perm(resource).require('BLOG_MODIFY_OWN')
        else:
            req.perm(resource).require('BLOG_MODIFY_ALL')
        post.categories = ""
        post.save(req.authname, 'Blog post categories removed via Tags plugin.')
