# -*- coding: utf-8 -*-
"""
Sample FullBlog plugin that shows examples of how to use the interfaces.

License: BSD

(c) 2008 ::: www.CodeResort.com - BV Network AS (simon-code@bvnetwork.no)
"""

from trac.core import *
from tracfullblog.api import IBlogChangeListener, IBlogManipulator
from tracfullblog.model import BlogComment

class SampleBlogPlugin(Component):
    
    implements(IBlogChangeListener, IBlogManipulator)
    
    # IBlogChangeListener methods

    def blog_post_changed(self, postname, version):
        if version == 1:
            text = "SampleBlogPlugin: Blog post '%s' created (version 1)."
            self.env.log.debug(text % postname)
        else:
            text = "SampleBlogPlugin: Version '%d' of blog post '%s' added."
            self.env.log.debug(text % (version, postname))

    def blog_post_deleted(self, postname, version, fields):
        if version == 0:
            text = "SampleBlogPlugin: Blog post %s deleted (all versions). " \
                   "Last version data: %s"
            self.env.log.debug(text % (postname, repr(fields)))
        else:
            text = "SampleBlogPlugin: Version '%d' of blog post '%s' " \
                   "deleted. Contents: %s"
            self.env.log.debug(text % (version, postname, repr(fields)))

    def blog_comment_added(self, postname, number):
        text = "SampleBlogPlugin: New comment number '%d' added " \
                "to blog post '%s'. Comment: %s"
        bc = BlogComment(self.env, postname, number)
        self.env.log.debug(text % (bc.number, bc.post_name, bc.comment))

    def blog_comment_deleted(self, postname, number, fields):
        if number == 0:
            text = "SampleBlogPlugin: All comments on blog post '%s' deleted."
            self.env.log.debug(text % (postname,))
        else:
            text = "SampleBlogPlugin: Comment number '%d' on blog " \
                    "post '%s' deleted. Comment: %s"
            self.env.log.debug(text % (number, postname, fields['comment']))

    # IBlogManipulator methods

    def validate_blog_post(self, req, postname, version, fields):
        """Validate blog post fields before they are to be inserted as new version.
        Fields is a dict of the fields needed for insert by model.BlogPost.
                
        Must return a list of `(field, message)` tuples, one for each problem
        detected. `field` can be `None` to indicate an overall problem with the
        post. Therefore, a return value of `[]` means everything is OK."""
        self.env.log.debug("SampleBlogPlugin: '%s' validation: %s" % (
                                                postname, repr(fields)))
        if fields['title'].lower().find('spam') != -1:
            return [('title', "A spammy title? None of that here, thanks.")]
        else:
            return []

    def validate_blog_comment(self, req, postname, fields):
        """Validate new blog fields before comment gets added to 'postname'
        Fields is a dict of the fields needed for insert by model.BlogComment.
        
        Must return a list of `(field, message)` tuples, one for each problem
        detected. `field` can be `None` to indicate an overall problem with the
        comment. Therefore, a return value of `[]` means everything is OK."""
        self.env.log.debug("SampleBlogPlugin: Comment validation: %s" % repr(fields))
        if fields['author'] == 'simon':
            return [('author', "Shifty character. Not trusted to make a comment.")]
        else:
            return []
