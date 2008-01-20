# -*- coding: utf-8 -*-
"""
TracFullBlog module with core components and functionality
shared across the various access interfaces and modules:
 * Permissions
 * Settings

License: BSD

(c) 2007 ::: www.CodeResort.com - BV Network AS (simon-code@bvnetwork.no)
"""

from genshi.builder import tag

from trac.attachment import ILegacyAttachmentPolicyDelegate
from trac.core import *
from trac.config import IntOption
from trac.perm import IPermissionRequestor
from trac.resource import IResourceManager
from trac.wiki.api import IWikiSyntaxProvider

# Relative imports (same package)
from api import IBlogChangeListener, IBlogManipulator
from model import BlogPost, BlogComment, get_blog_resources


class FullBlogCore(Component):
    """ Module implementing features that are common and shared
    between the various parts of the plugin. """

    # Extensions
    
    listeners = ExtensionPoint(IBlogChangeListener)
    manipulators = ExtensionPoint(IBlogManipulator)
    
    # Options
    
    IntOption('fullblog', 'num_items_front', 20,
        """Option to specify how many recent posts to display on the
        front page of the Blog.""")

    default_pagename = 'change_this_post_shortname'
    reserved_names = ['create', 'view', 'edit', 'delete',
                    'archive', 'category', 'author']
    
    implements(IPermissionRequestor, IWikiSyntaxProvider, IResourceManager,
            ILegacyAttachmentPolicyDelegate)

    # IPermissionRequestor method
    
    def get_permission_actions(self):
        """ Permissions supported by the plugin.
        Commenting needs special enabling if wanted as it is only enabled
        if user is ADMIN or if specifically given BLOG_COMMENT permission.
        Apart from that, the permisions follow regular practice of builing
        on top of each other. """
        return ['BLOG_VIEW',
                ('BLOG_COMMENT', ['BLOG_VIEW']),
                ('BLOG_CREATE', ['BLOG_VIEW']),
                ('BLOG_MODIFY_OWN', ['BLOG_CREATE']),
                ('BLOG_MODIFY_ALL', ['BLOG_MODIFY_OWN']),
                ('BLOG_ADMIN', ['BLOG_MODIFY_ALL', 'BLOG_COMMENT']),
                ]

    # ILegacyAttachmentPolicyDelegate methods
    
    def check_attachment_permission(self, action, username, resource, perm):
        """ Respond to the various actions into the legacy attachment
        permissions used by the Attachment module. """
        if resource.parent.realm == 'blog':
            if action == 'ATTACHMENT_VIEW':
                return 'BLOG_VIEW' in perm(resource.parent)
            if action in ['ATTACHMENT_CREATE', 'ATTACHMENT_DELETE']:
                if 'BLOG_MODIFY_ALL' in perm(resource.parent):
                    return True
                elif 'BLOG_MODIFY_OWN' in perm(resource.parent):
                    bp = BlogPost(self.env, resource.parent.id)
                    if bp.author == username:
                        return True
                    else:
                        return False
                else:
                    return False

    # IResourceManager methods
    
    def get_resource_realms(self):
        yield 'blog'

    def get_resource_url(self, resource, href, **kwargs):
        return href.blog(resource.id,
                resource.version and 'version=%d' % (resource.version) or None)
        
    def get_resource_description(self, resource, format=None, context=None,
                                 **kwargs):
        bp = BlogPost(self.env, resource.id, resource.version)
        if context:
            return tag.a('Blog: '+bp.title, href=context.href.blog(resource.id))
        else:
            return 'Blog: '+bp.title

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('blog', self._bloglink_formatter)
    
    def _bloglink_formatter(self, formatter, ns, object, label):
        object = (object.startswith('/') and object[1:]) or object
        if not object:
            return tag.a(label, href=formatter.href.blog(object))
        if object[:3].isdigit() and object[4] == '/':
            # Requesting a period listing
            return tag.a(label, href=formatter.href.blog(object))
        elif [item for item in self.reserved_names if (
                    object == item or object.startswith(item+'/'))]:
            # Requesting a specific path to command or listing
            return tag.a(label, href=formatter.href.blog(object))
        else:
            # Assume it is a regular post, and pass to 'view'
            return tag.a(label, href=formatter.href.blog(object))

    # Utility methods used by other modules
    
    def get_bloginfotext(self):
        """ Retrieves the blog info text in sidebar from database. """
        try:
            cnx = self.env.get_db_cnx()
            cursor = cnx.cursor()
            cursor.execute("SELECT value from system " \
                "WHERE name='fullblog_infotext'")
            rows = cursor.fetchall()
            if rows:
                return rows[0][0] # Only item in cursor (hopefully)
            else:
                return ''
        except:
            return ''

    def set_bloginfotext(self, text=''):
        """ Stores the blog info text in the database. """
        try:
            cnx = self.env.get_db_cnx()
            cursor = cnx.cursor()
            cursor.execute("UPDATE system set value=%s " \
                "WHERE name=%s", (text, 'fullblog_infotext'))
            cnx.commit()
            return True
        except:
            return False
    
    def get_prev_next_posts(self, perm, post_name):
        """ Returns the name of the next and previous posts when compared with
        input 'post_name'. """
        prev = next = marker = ''
        found = False
        for post in get_blog_resources(self.env):
            if not 'BLOG_VIEW' in perm(post):
                continue
            if post.id == post_name:
                next = marker
                found = True
                continue
            if found:
                prev = post.id
                break
            marker = post.id
        return prev, next

    # CRUD methods that support input verification and listener and manipulator APIs
    
    def create_post(self, req, bp, version_author, version_comment=u'', verify_only=False):
        """ Creates a new post, or a new version of existing post.
        Does some input verification.
        Supports manipulator and listener plugins.
        Returns [] for success, or a list of (field, message) tuples if not."""
        warnings = []
        # Do basic checking for content existence
        warnings.extend(bp.save(version_author, version_comment, verify_only=True))
        # Do some more fundamental checking
        if bp.name in self.reserved_names:
            warnings.append((req, "'%s' is a reserved name. Please change." % bp.name))
        if bp.name == self.default_pagename:
            warnings.append(('post_name', "The default page shortname must be changed."))
        # Check if any plugins has objections with the contents
        fields = {
            'title': bp.title,
            'body': bp.body,
            'author': bp.author,
            'version_comment': version_comment,
            'version_author': version_author,
            'categories': bp.categories,
            'category_list': bp.category_list}
        for manipulator in self.manipulators:
            warnings.extend(manipulator.validate_blog_post(
                            req, bp.name, bp.version, fields))
        if warnings or verify_only:
            return warnings
        # All seems well - save and notify
        warnings.extend(bp.save(version_author, version_comment))
        for listener in self.listeners:
            listener.blog_post_changed(bp.name, bp.version)
        return warnings
        
    def delete_post(self, bp, version=0):
        """ Deletes a blog post (version=0 for all versions, or specific version=N).
        Notifies listeners if successful.
        Returns [] for success, or a list of (field, message) tuples if not."""
        warnings = []
        fields = bp._fetch_fields(version)
        if not fields:
            warnings.append(('', "Post and/or version does not exist."))
        # Inital checking. Return if there are problems.
        if warnings:
            return warnings
        # Do delete
        is_deleted = bp.delete(version)
        if not is_deleted:
            warnings.append(('', "Unknown error. Not deleted."))
        if is_deleted:
            version = bp.get_versions() and fields['version'] or 0 # Any versions left?
            for listener in self.listeners:
                    listener.blog_post_deleted(bp.name, version, fields)
                    if not version: # Also notify that all comments are deleted
                        listener.blog_comment_deleted(bp.name, 0, {})
        return warnings
    
    def create_comment(self, req, bc, verify_only=False):
        """ Create a comment. Comment and author set on the bc (comment) instance:
        * Calls manipulators and bc.create() (if not verify_only) collecting warnings
        * Calls listeners on success
        Returns [] for success, or a list of (field, message) tuples if not."""
        # Check for errors
        warnings = []
        # Verify the basics such as content existence, duplicates, post existence
        warnings.extend(bc.create(verify_only=True))
        # Now test plugins to see if new issues are raised.
        fields = {'comment': bc.comment,
                  'author': bc.author}
        for manipulator in self.manipulators:
            warnings.extend(
                manipulator.validate_blog_comment(req, bc.post_name, fields))
        if warnings or verify_only:
            return warnings
        # No problems (we think), try to save.
        warnings.extend(bc.create())
        if not warnings:
            for listener in self.listeners:
                listener.blog_comment_added(bc.post_name, bc.number)
        return warnings
    
    def delete_comment(self, bc):
        """ Deletes the comment (bc), and notifies listeners.
        Returns [] for success, or a list of (field, message) tuples if not."""
        warnings = []
        fields = {'post_name': bc.post_name,
                  'number': bc.number,
                  'comment': bc.comment,
                  'author': bc.author,
                  'time': bc.time}
        is_deleted = bc.delete()
        if is_deleted:
            for listener in self.listeners:
                listener.blog_comment_deleted(
                        fields['post_name'], fields['number'], fields)
        else:
            warnings.append(('', "Unknown error. Not deleted."))
        return warnings
