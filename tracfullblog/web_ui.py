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
from operator import itemgetter

# Trac and Genshi imports
from genshi.builder import tag
from trac.attachment import AttachmentModule
from trac.config import ListOption
from trac.core import *
from trac.mimeview.api import Context
from trac.resource import Resource
from trac.search.api import ISearchSource, shorten_result
from trac.timeline.api import ITimelineEventProvider
from trac.util.compat import sorted
from trac.util.datefmt import to_datetime, to_unicode, utc, localtz
from trac.util.translation import _
from trac.web.api import IRequestHandler, HTTPNotFound
from trac.web.chrome import INavigationContributor, ITemplateProvider, \
                            add_stylesheet, add_warning, add_ctxtnav
from trac.wiki.formatter import format_to_oneliner, format_to_html

# Imports from same package
from model import *
from core import FullBlogCore
from util import map_month_names, parse_period

__all__ = ['FullBlogModule']


class FullBlogModule(Component):
    
    implements(IRequestHandler, INavigationContributor,
               ISearchSource, ITimelineEventProvider,
               ITemplateProvider)

    ListOption('fullblog', 'month_names',
        doc = """Ability to specify a list of month names for display in groupings.
        If empty it will make a list from default locale setting.
        Enter list of 12 months like:
        `month_names = January, February, ..., December` """)

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
        if 'BLOG_VIEW' in req.perm('blog'):
            yield ('mainnav', 'blog',
                   tag.a(_('Blog'), href=req.href.blog()) )

    # IRequstHandler methods
    
    def match_request(self, req):
        """Return whether the handler wants to process the given request."""
        match = re.match(r'^/blog(?:/(.*)|$)', req.path_info)
        if 'BLOG_VIEW' in req.perm('blog') and match:
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
        path_items = req.args.get('blog_path', '').split('/')
        path_items = [item for item in path_items if item] # clean out empties
        action = req.args.get('action', 'view').lower()
        try:
            version = int(req.args.get('version', 0))
        except:
            version = 0
        command = pagename = ''
        command = (len(path_items) and path_items[0]) or ''
        if command.lower() in [u'view', u'edit'] and len(path_items) == 2:
            pagename = path_items[1]
        if command and command not in [
                'view', 'edit', 'create', 'archive']:
            if len(path_items) == 1:
                # Assume it is a request for a specific post
                pagename = command
                command = 'view'
            else:
                # Assume it is a listing, do further parsing later
                command = 'listing'

        data = {}

        template = 'fullblog_view.html'
        data['blog_about'] = BlogPost(self.env, 'about')
        data['blog_infotext'] = blog_core.get_bloginfotext()
        blog_month_names = map_month_names(
                    self.env.config.getlist('fullblog', 'month_names'))
        data['blog_month_names'] = blog_month_names
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

        elif command == 'view' and pagename:
            # Requesting a specific blog post
            the_post = BlogPost(self.env, pagename, version)
            if not the_post.version:
                raise HTTPNotFound("No blog post named '%s'." % pagename)
            if req.method == 'POST':   # Adding/Previewing a comment
                # Permission?
                req.perm(the_post.resource).require('BLOG_COMMENT')
                comment = BlogComment(self.env, pagename)
                comment.comment = req.args.get('comment', '')
                comment.author = (req.authname != 'anonymous' and req.authname) \
                            or req.args.get('author')
                comment.time = datetime.datetime.now(utc)
                if 'cancelcomment' in req.args:
                    req.redirect(req.href.blog(pagename))                
                elif 'previewcomment' in req.args:
                    data['blog_comment'] = comment
                elif 'submitcomment' in req.args:
                    comment.create()
                    req.redirect(req.href.blog(pagename
                                )+'#comment-'+str(comment.number))
            data['blog_post'] = the_post
            context = Context.from_request(req, the_post.resource)
            data['context'] = context
            data['blog_attachments'] = AttachmentModule(self.env).attachment_data(context)

        elif command in ['create', 'edit']:
            template = 'fullblog_edit.html'
            pagename = pagename or req.args.get('name','') or default_pagename
            the_post = BlogPost(self.env, pagename)
            if req.method == 'POST':   # Create or edit a blog post
                if 'blog-cancel' in req.args:
                    if req.args.get('action','') == 'edit':
                        req.redirect(req.href.blog(pagename))
                    else:
                        req.redirect(req.href.blog())
                # Assert permissions
                if command == 'create':
                    req.perm(Resource('blog', None)).require('BLOG_CREATE')
                elif command == 'edit':
                    if the_post.author == req.authname:
                        req.perm(the_post.resource).require('BLOG_MODIFY_OWN')
                    else:
                        req.perm(the_post.resource).require('BLOG_MODIFY_ALL')
                # Input verifications and warnings
                if command == 'create' and the_post.version:
                    add_warning(req, "A post named '%s' already exists. " % (
                            the_post.name,))
                    the_post = BlogPost(self.env, default_pagename)
                elif the_post.name == default_pagename:
                    add_warning(req, "The default page shortname must be changed.")
                elif the_post.name in reserved_names:
                    add_warning(req, "'%s' is a reserved name. Please change." % (
                                    the_post.name,))
                orig_author = the_post.author
                is_updated = the_post.update_fields(req.args)
                if not the_post.title:
                    add_warning(req, "Title required.")
                if not the_post.body:
                    add_warning(req, "Blog post body required.")
                version_comment = req.args.get('new_version_comment', '')
                if 'blog-preview' in req.args:
                    context = Context.from_request(req, the_post.resource)
                    data['context'] = context
                    data['blog_attachments'] = AttachmentModule(self.env).attachment_data(context)
                    data['blog_action'] = 'preview'
                    data['blog_version_comment'] = version_comment
                    if (orig_author and orig_author != the_post.author) and (
                            not 'BLOG_MODIFY_ALL' in req.perm(the_post.resource)):
                        add_warning(req, "If you change the author you cannot " \
                            "edit the post again due to restricted permissions.")
                        data['blog_orig_author'] = orig_author
                elif 'blog-save' in req.args:
                    if not is_updated:
                        add_warning("No changes made. New version not created.")
                    if not req.chrome['warnings']:
                        the_post.save(req.authname,
                                version_comment)
                        req.redirect(req.href.blog(the_post.name))
            data['blog_edit'] = the_post

        elif command == 'listing':
            # 2007/10 or category/something or author/theuser
            title = category = author = ''
            from_dt, to_dt = parse_period(path_items)
            if from_dt:
                title = "Posts for the month of %s %d" % (
                        blog_month_names[from_dt.month -1], from_dt.year)

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
        if 'BLOG_CREATE' in req.perm('blog'):
            add_ctxtnav(req, 'New Post', href=req.href.blog('create'),
                    title="Create new Blog Post")
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
        if 'BLOG_VIEW' in req.perm('blog', id=None):
            yield ('blog_posts', 'Blog Posts')
            yield ('blog_comments', 'Blog Comments')

    def get_search_results(self, req, terms, filters):
        """Return a list of search results matching each search term in `terms`.
        
        The `filters` parameters is a list of the enabled filters, each item
        being the name of the tuples returned by `get_search_events`.

        The events returned by this function must be tuples of the form
        `(href, title, date, author, excerpt).`
        """
        blog_realm = Resource('blog')
        if not 'BLOG_VIEW' in req.perm(blog_realm):
            return
        if 'blog_posts' in filters:
            results = search_blog_posts(self.env, terms)
            for name, version, publish_time, author, title, body in results:
                bp_resource = blog_realm(id=name, version=version)
                if 'BLOG_VIEW' in req.perm(bp_resource):
                    yield (req.href.blog(name), 'Blog: '+title,
                        publish_time, author, shorten_result(
                                text=body, keywords=terms))
        if 'blog_comments' in filters:
            results = search_blog_comments(self.env, terms)
            for post_name, comment_number, comment, comment_author, \
                    comment_time in results:
                bp_resource = blog_realm(id=post_name, version=None)
                if 'BLOG_VIEW' in req.perm(bp_resource):
                    bp = BlogPost(self.env, post_name)
                    yield (req.href.blog(
                            post_name)+'#comment-'+str(comment_number),
                        'Blog: '+bp.title+' (Comment '+str(comment_number)+')',
                        comment_time, comment_author,
                        shorten_result(text=comment, keywords=terms))
    
    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'BLOG_VIEW' in req.perm('blog', id=None):
            yield ('blog', _('Blog details'))

    def get_timeline_events(self, req, start, stop, filters):
        if 'blog' in filters:
            blog_realm = Resource('blog')
            if not 'BLOG_VIEW' in req.perm(blog_realm):
                return
            add_stylesheet(req, 'tracfullblog/css/fullblog.css')

        if 'blog' in filters and req.args.get('view', '').lower() == 'full':
            # Full style blog posts
            category = req.args.get('category', '')
            author = req.args.get('author', '')
            blog_posts = get_blog_posts(self.env, from_dt=start, to_dt=stop,
                            author=author, category=category, all_versions=False)
            for name, version, time, author, title, body, category_list \
                    in blog_posts:
                bp_resource = blog_realm(id=name)
                if 'BLOG_VIEW' not in req.perm(bp_resource):
                    continue
                bp = BlogPost(self.env, name) # Use last version
                yield ('blog', bp.publish_time, bp.author,
                            (bp_resource, bp, None, 'full'))
        elif 'blog' in filters:
            # Blog posts
            blog_posts = get_blog_posts(self.env, from_dt=start, to_dt=stop,
                                        all_versions=True)
            for name, version, time, author, title, body, category_list \
                    in blog_posts:
                bp_resource = blog_realm(id=name, version=version)
                if 'BLOG_VIEW' not in req.perm(bp_resource):
                    continue
                bp = BlogPost(self.env, name, version=version)
                yield ('blog', bp.version_time, bp.version_author,
                            (bp_resource, bp, None, 'detail'))
            # Attachments (will be rendered by attachment module)
            for event in AttachmentModule(self.env).get_timeline_events(
                req, blog_realm, start, stop):
                yield event
            # Blog comments
            blog_comments = get_blog_comments(self.env, from_dt=start, to_dt=stop)
            blog_comments = sorted(blog_comments, key=itemgetter(4), reverse=True)
            for post_name, number, comment, author, time in blog_comments:
                bp_resource = blog_realm(id=post_name)
                if 'BLOG_VIEW' not in req.perm(bp):
                    continue
                bp = BlogPost(self.env, post_name)
                bc = BlogComment(self.env, post_name, number=number)
                yield ('blog', time, author, (bp_resource, bp, bc, 'detail'))

    def render_timeline_event(self, context, field, event):
        bp_resource, bp, bc, view = event[3]
        if bc: # A blog comment
            if field == 'url':
                return context.href.blog(bp.name) + '#comment-%d' % bc.number
            elif field == 'title':
                return tag('Blog: ', tag.em(bp.title), ' comment added')
            elif field == 'description':
                return format_to_oneliner(self.env,
                            context(resource=bp_resource), bc.comment)
        else: # A blog post
            if field == 'url':
                return context.href.blog(bp.name)
            elif field == 'title':
                if view=='full':
                    return tag(tag.em(bp.title))
                else:
                    return tag('Blog: ', tag.em(bp.title),
                            bp.version > 1 and ' edited' or ' created')
            elif field == 'description':
                if view == 'full':
                    # Full blog view
                    return format_to_html(self.env,
                        context.from_request(context.req,
                                resource=bp_resource, absurls=True),
                        bp.body)
                else:
                    # Any other regular display format
                    return format_to_oneliner(self.env,
                            context(resource=bp_resource),
                            bp.version==1 and bp.body or bp.version_comment)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        """ Makes the 'htdocs' folder inside the egg available. """
        return [('tracfullblog', resource_filename('tracfullblog', 'htdocs'))]

    def get_templates_dirs(self):
        """ Location of Trac templates provided by plugin. """
        return [resource_filename('tracfullblog', 'templates')]
