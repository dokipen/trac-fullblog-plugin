# -*- coding: utf-8 -*-
"""
Wiki Macros for the plugin.

License: BSD

(c) 2007 ::: www.CodeResort.com - BV Network AS (simon-code@bvnetwork.no)
"""

from genshi.builder import tag

from trac.core import TracError
from trac.util.datefmt import to_datetime, utc, format_datetime
from trac.web.chrome import add_stylesheet, Chrome
from trac.wiki.api import parse_args
from trac.wiki.macros import WikiMacroBase

from model import get_blog_posts, BlogPost
from util import parse_period

class BlogListMacro(WikiMacroBase):
    """A macro to display list of posts and extracts outside (or inside)
    the Blog module - most commonly Wiki pages.

    All arguments are optional:
    {{{
    [[BlogList]]
    }}}

    Example showing all available named arguments:
    {{{
    [[BlogList(recent=5, category=trac, period=2007/12, author=osimons, format=float, heading=Some Trac Posts)]]
    }}}
    
    The arguments for criteria are 'AND'-based, so the above example will render
    at most 5 posts by 'osimons' in December 2007 with category 'trac'. 
    
    There is no heading unless specified.
    
    Without restriction on recent number of posts, it will use the number currently
    active in the Blog module as default for 'float' and 'full' rendering, but for rendering
    of 'inline' list it will render all found as default unless restricted.
    
    The `format=` keyword argument supports rendering these formats:
    ||`format=inline`||Renders an unordered list in the normal text flow (default).||
    ||`format=float`||A floating box out on the side of the page with slightly more detail.||
    ||`format=full`||Full rendering like on period, category and author listings inside blog.||
    
    The arguments can appear in any order.
    
    Posts are rendered sorted by newest first for all modes.
    """
    
    def expand_macro(self, formatter, name, content):

        # Parse content for arguments
        args_list, args_dict = parse_args(content)
        from_dt, to_dt = parse_period(list(args_dict.get('period', '').split('/')))
        category = args_dict.get('category', '')
        author = args_dict.get('author', '')
        recent = int(args_dict.get('recent', 0))
        format = args_dict.get('format', 'inline').lower()
        heading = args_dict.get('heading', '')

        # Get blog posts
        all_posts = get_blog_posts(self.env, author=author, category=category,
                        from_dt=from_dt, to_dt=to_dt)

        # Trim posts against permissions and count
        post_list = []
        post_instances = []
        if format in ['float', 'full']:
            recent = recent or self.env.config.getint('fullblog', 'num_items_front')
        recent = recent or len(all_posts)
        count = 0
        for post in all_posts:
            if count == recent:
                break
            bp = BlogPost(self.env, post[0])
            if 'BLOG_VIEW' in formatter.req.perm(bp.resource):
                count += 1
                post_instances.append(bp)
                post_list.append(post)

        # Rendering
        add_stylesheet(formatter.req, 'tracfullblog/css/fullblog.css')

        if format == 'inline':
            data = {'heading': heading,
                    'posts': post_list,
                    'execute_blog_macro': True}
            return Chrome(self.env).render_template(formatter.req,
                    'fullblog_macro_monthlist.html', data=data, fragment=True)

        elif format == 'full':
            return self._render_full_format(formatter, post_list,
                                            post_instances, heading)

        elif format == 'float':
            # Essentially a 'full' list - just wrapped inside a new div
            return tag.div(self._render_full_format(formatter, post_list,
                                            post_instances, heading),
                            class_="blogflash")

        else:
            raise TracError("Invalid 'format' argument used for macro %s." % name)

    def _render_full_format(self, formatter, post_list, post_instances, heading):
        """ Renters full blog posts. """
        out = tag.div(class_="blog")
        out.append(tag.div(heading, class_="blog-list-title"))
        for post in post_instances:
            data = {'post': post,
                    'list_mode': True,
                    'execute_blog_macro': True}
            out.append(Chrome(self.env).render_template(formatter.req,
                'fullblog_macro_post.html', data=data, fragment=True))
        return out
