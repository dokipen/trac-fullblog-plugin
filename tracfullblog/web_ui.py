# -*- coding: utf-8 -*-
"""
Interface code for the plugin.
Various providers for menus and request handling.

License: BSD

(c) 2007 ::: www.CodeResort.com - BV Network AS (simon-code@bvnetwork.no)
"""

# Imports from standard lib
import datetime
import re
from pkg_resources import resource_filename

# Trac and Genshi imports
from genshi.builder import tag
from trac.core import *
from trac.search.api import ISearchSource, shorten_result
from trac.util.datefmt import to_datetime, to_unicode, localtz
from trac.util.translation import _
from trac.web.api import IRequestHandler, HTTPNotFound
from trac.web.chrome import INavigationContributor, ITemplateProvider, \
                            add_stylesheet

# Imports from same package
from model import *
from core import FullBlogCore

__all__ = ['FullBlogModule']

# Utility functions

def add_months(thedate, months):
    "Add <months> months to <thedate>."
    y, m, d = thedate.timetuple()[:3]
    y2, m2 = divmod(m + months - 1, 12)
    return datetime.datetime(y + y2, m2 + 1, d, tzinfo=thedate.tzinfo)

# UI class

class FullBlogModule(Component):
    
    implements(IRequestHandler, INavigationContributor,
               ISearchSource, ITemplateProvider)

    # INavigationContributor methods
    
    def get_active_navigation_item(self, req):
        """This method is only called for the `IRequestHandler` processing the
        request.
        
        It should return the name of the navigation item that should be
        highlighted as active/current.
        """
        return 'blog'

    def get_navigation_items(self, req):
        """Should return an iterable object over the list of navigation items to
        add, each being a tuple in the form (category, name, text).
        """
        if 'BLOG_VIEW' in req.perm:
            yield ('mainnav', 'blog',
                   tag.a(_('Blog'), href=req.href.blog()) )

    # IRequstHandler methods
    
    def match_request(self, req):
        """Return whether the handler wants to process the given request."""
        match = re.match(r'^/blog(?:/(.*)|$)', req.path_info)
        if 'BLOG_VIEW' in req.perm and match:
            req.args['blog_path'] = ''
            if match.group(1):
                req.args['blog_path'] = match.group(1)
            return True

    def process_request(self, req):
        """ Processing the request. """

        blog_core = FullBlogCore(self.env)
        default_pagename = 'change_this_post_shortname'
        reserved_names = blog_core.reserved_names
        
        # Parse out the path and actions from args
        path_items = req.args.get('blog_path').split('/')
        path_items = [item for item in path_items if item] # clean out empties
        action = req.args.get('action', 'view').lower()
        version = req.args.get('version', 0)
        command = pagename = ''
        command = (len(path_items) and path_items[0].lower()) or ''
        if command in [u'view', u'edit'] and len(path_items) == 2:
            pagename = path_items[1]
        if command and command not in [
                'view', 'edit', 'create', 'archive', 'about']:
            command = 'listing'      # do further parsing later

        data = {}

        template = 'fullblog_view.html'
        data['blog_about'] = BlogPost(self.env, 'about')
        data['blog_infotext'] = blog_core.get_bloginfotext()

        self.env.log.debug(
            "Blog debug: command=%r, pagename=%r, path_items=%r" % (
                command, pagename, path_items))

        if not command:
            # Request for just root (display latest)
            data['blog_post_list'] = []
            count = 0
            maxcount = self.env.config.getint('fullblog', 'num_items_front')
            data['blog_list_title'] = "Recent posts (max %d) " \
                        "- Browse or Archive for more" % maxcount
            for post in get_blog_posts(self.env):
                count += 1
                if count == maxcount:
                    # Only display a certain number on front page (from config)
                    break
                data['blog_post_list'].append(
                        BlogPost(self.env, post[0], post[1]))

        elif command == 'archive':
            # Requesting the archive page
            template = 'fullblog_archive.html'
            data['blog_archive'] = group_posts_by_month(get_blog_posts(self.env))

        elif command == 'about':
            # The '/about' page - basically a post named 'about' so we redirect
            if data['blog_about'].version:
                # Exists, redirect to post read
                req.redirect(req.href.blog('view', 'about'))
            else:
                req.redirect(req.href.blog('create', name='about'))

        elif command == 'view' and pagename:
            # Requesting a specific blog post
            the_post = BlogPost(self.env, pagename, version)
            if not the_post.version:
                raise HTTPNotFound("No blog post named '%s'." % pagename)
            if req.method == 'POST':   # Adding/Previewing a comment
                # Permission?
                req.perm.require('BLOG_COMMENT')
                comment = BlogComment(self.env, pagename)
                comment.comment = req.args.get('comment', '')
                comment.author = (req.authname != 'anonymous' and req.authname) or req.args.get('author')
                comment.time = to_datetime(None)
                if 'cancelcomment' in req.args:
                    req.redirect(req.href.blog('view', pagename))                
                elif 'previewcomment' in req.args:
                    data['blog_comment'] = comment
                elif 'submitcomment' in req.args:
                    comment.create()
                    req.redirect(req.href.blog('view', pagename
                                )+'#comment-'+str(comment.number))
            data['blog_post'] = the_post

        elif command in ['create', 'edit']:
            template = 'fullblog_edit.html'
            pagename = pagename or req.args.get('name','') or default_pagename
            the_post = BlogPost(self.env, pagename)
            if req.method == 'POST':   # Create or edit a blog post
                if 'blog-cancel' in req.args:
                    if req.args.get('action','') == 'edit':
                        req.redirect(req.href.blog('view', pagename))
                    else:
                        req.redirect(req.href.blog())
                # Assert permissions
                if command == 'create':
                    req.perm.require('BLOG_CREATE')
                elif command == 'edit':
                    if the_post.author == req.authname:
                        req.perm.require('BLOG_MODIFY_OWN')
                    else:
                        req.perm.require('BLOG_MODIFY_ALL')
                # Input verifications and warnings
                if command == 'create' and the_post.version:
                    req.warning("A post named '%s' already exists. " % (
                            the_post.name,))
                    the_post = BlogPost(self.env, default_pagename)
                elif the_post.name == default_pagename:
                    req.warning("The default page shortname must be changed.")
                elif the_post.name in reserved_names:
                    req.warning("'%s' is a reserved name. Please change." % (
                                    the_post.name,))
                orig_author = the_post.author
                is_updated = the_post.update_fields(req.args)
                if not the_post.title:
                    req.warning("Title required.")
                if not the_post.body:
                    req.warning("Blog post body required.")
                version_comment = req.args.get('new_version_comment', '')
                if 'blog-preview' in req.args:
                    data['blog_action'] = 'preview'
                    data['blog_version_comment'] = version_comment
                    if (orig_author and orig_author != the_post.author) and (
                            not 'BLOG_MODIFY_ALL' in req.perm):
                        req.warning("If you change the author you cannot " \
                            "edit the post again due to restricted permissions.")
                        data['blog_orig_author'] = orig_author
                elif 'blog-save' in req.args:
                    if not is_updated:
                        req.warning("No changes made. New version not created.")
                    if not req.warnings:
                        the_post.save(req.authname,
                                version_comment)
                        req.redirect(req.href.blog('view', the_post.name))
            data['blog_edit'] = the_post

        elif command == 'listing':
            # 2007/10 or category/something or author/theuser
            title = category = author = ''
            try:
                # Test for year and month values
                year = int(path_items[0])
                month = int(path_items[1])
                from_dt = datetime.datetime(year, month, 1, tzinfo=localtz)
                to_dt = add_months(from_dt, months=1)
                title = "Posts for the month of %s" % (
                        to_unicode(from_dt.strftime('%B %Y')),)
            except ValueError:
                # Not integers, ignore
                to_dt = from_dt = None
            category = (path_items[0].lower() == 'category'
                        and path_items[1]) or ''
            if category:
                title = "Posts in category %s" % category
            author = (path_items[0].lower() == 'author'
                        and path_items[1]) or ''
            if author:
                title = "Posts by author %s" % author
            if not (author or category or (from_dt and to_dt)):
                raise HTTPNotFound("Not a valid path for viewing blog posts.")
            data['blog_post_list'] = [BlogPost(self.env, post[0],
                        post[1]) for post in get_blog_posts(self.env,
                        category=category, author=author, 
                        from_dt=from_dt, to_dt=to_dt)]
            data['blog_list_title'] = title

        else:
            raise HTTPNotFound("Not a valid blog path.")

        data['blog_months'], data['blog_authors'], data['blog_categories'], \
                data['blog_total'] = get_months_authors_categories(self.env)
        
        add_stylesheet(req, 'tracfullblog/css/fullblog.css')
        return (template, data, None)
    
    # ISearchSource methods
    
    def get_search_filters(self, req):
        """Return a list of filters that this search source supports.
        
        Each filter must be a `(name, label[, default])` tuple, where `name` is
        the internal name, `label` is a human-readable name for display and
        `default` is an optional boolean for determining whether this filter
        is searchable by default.
        """
        yield ('blog_posts', 'Blog Posts')
        yield ('blog_comments', 'Blog Comments')

    def get_search_results(self, req, terms, filters):
        """Return a list of search results matching each search term in `terms`.
        
        The `filters` parameters is a list of the enabled filters, each item
        being the name of the tuples returned by `get_search_events`.

        The events returned by this function must be tuples of the form
        `(href, title, date, author, excerpt).`
        """
        if 'blog_posts' in filters:
            results = search_blog_posts(self.env, terms)
            for name, version, publish_time, author, title, body in results:
                yield (req.href.blog('view', name), 'Blog: '+title,
                    publish_time, author, shorten_result(
                            text=body, keywords=terms))
        if 'blog_comments' in filters:
            results = search_blog_comments(self.env, terms)
            for post_name, comment_number, comment, comment_author, \
                    comment_time in results:
                bp = BlogPost(self.env, post_name)
                yield (req.href.blog(
                        'view', post_name)+'#comment-'+str(comment_number),
                    'Blog: '+bp.title+' (Comment '+str(comment_number)+')',
                    comment_time, comment_author,
                    shorten_result(text=comment, keywords=terms))
    
    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        """ Makes the 'htdocs' folder inside the egg available. """
        return [('tracfullblog', resource_filename('tracfullblog', 'htdocs'))]

    def get_templates_dirs(self):
        """ Location of Trac templates provided by plugin. """
        return [resource_filename('tracfullblog', 'templates')]
