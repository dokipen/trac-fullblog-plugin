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

from trac.core import *
from trac.config import IntOption
from trac.perm import IPermissionRequestor, IPermissionPolicy
from trac.resource import IResourceManager
from trac.wiki.api import IWikiSyntaxProvider

# Relative imports (same package)
from model import BlogPost, BlogComment


class FullBlogCore(Component):
    
    # Options
    
    IntOption('fullblog', 'num_items_front', 10,
        """Option to specify how many recent posts to display on the
        front page of the Blog.""")

    reserved_names = ['create', 'view', 'edit', 'delete',
                    'archive', 'category', 'author']
    
    implements(IPermissionRequestor, IWikiSyntaxProvider, IResourceManager,
            IPermissionPolicy)

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

    # IPermissionPolicy methods
    
    def check_permission(self, action, username, resource, perm):
        """ Need to map the various actions into the legacy attachment permissions
        used by the Attachment module. """
        if resource and resource.realm == 'attachment' and resource.parent.realm == 'blog':
            if action == 'ATTACHMENT_VIEW':
                return 'BLOG_VIEW' in perm(resource.parent)
            if action in ['ATTACHMENT_CREATE', 'ATTACHMENT_DELETE']:
                if 'BLOG_MODIFY_ALL' in perm(resource.parent.realm):
                    return True
                elif 'BLOG_MODIFY_OWN' in perm(resource.parent.realm):
                    bp = BlogPost(self.env, resource.parent.id)
                    if bp.author == username:
                        return True
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
            return tag.a(bp.title, href=context.href.blog(resource.id))
        else:
            return bp.title

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