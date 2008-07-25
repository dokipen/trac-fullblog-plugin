#!/bin/env python

# -*- coding: utf-8 -*-
# Copyright (C) 2008 John Hampton <pacopablo@pacopablo.com>
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 3. The name of the author may not be used to endorse or promote
#    products derived from this software without specific prior
#    written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR `AS IS'' AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
# GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Author: John Hampton <pacopablo@pacopablo.com>
# Contributor: risto.kankkunen@iki.fi

import sys
import time
import re
import os
from optparse import OptionParser

from trac.env import Environment
from trac.wiki.model import WikiPage
from trac.test import Mock, MockPerm
from trac.attachment import Attachment


_title_split_match = re.compile(r'\s*^=+\s+([^\n\r=]+?)\s+=+\s+(.+)$',
                                re.MULTILINE|re.DOTALL).match

_tag_split = re.compile('[,\s]+')

def split_tags(tags):
    """ Split the tags into a list """
    return  [t.strip() for t in _tag_split.split(tags) if t.strip()]

def epochtime(t):
    """ Return seconds from epoch from a datetime object """
    return int(time.mktime(t.timetuple()))

def insert_blog_post(cnx, name, version, title, body, publish_time, 
                     version_time, version_comment, version_author, 
                     author, categories):
    """ Insert the post into the FullBlog tables """
    cur = cnx.cursor()
    try:
        cur.execute("INSERT INTO fullblog_posts "
                    "(name, version, title, body, publish_time, version_time, "
                    "version_comment, version_author, author, categories) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (name, version, title, body, epochtime(publish_time),
                    epochtime(version_time), version_comment, version_author,
                    author, categories))
    except Exception, e:
        print("Unable to insert %s into the FullBlog: %s" % (name, e))
        raise

def reparent_blog_attachments(env, orig_name, new_name):
    """ Re-associate blog post attachments to FullBlog posts """
    cnx = env.get_db_cnx()
    cur = cnx.cursor()

    new_dir = Attachment(env, 'blog', new_name).path

    attachment_paths = list()
    for attachment in Attachment.select(env, 'wiki', orig_name):
        if os.path.exists(os.path.join(new_dir, attachment.filename)):
            print "Attachment", attachment.filename, "already where it should be"
            continue
        if not os.path.exists(attachment.path):
            raise Exception("Cannot find attachment %s for post %s" % (
                attachment.filename, orig_name
            ))
        attachment_paths.append(attachment.path)

    try:
        cur.execute(
            "UPDATE attachment "
            "SET type = 'blog', id = %s "
            "WHERE type = 'wiki' AND id = %s",
            (new_name, orig_name)
        )
    except Exception, e:
        print("Unable to import blog attachment %s into the FullBlog: %s" % (orig_name, e))
        raise

    if not attachment_paths:
        return

    for p in attachment_paths:
        try:
            new_p = os.path.join(new_dir, os.path.basename(p))
            print "Moving attachment"
            print "   from", p
            print "   to  ", new_p
            os.renames(p, new_p)
        except Exception, e:
            print "Failed to move %s: %s" % (p, e)
            raise

def Main(opts):
    """ Cross your fingers and pray """
    env = Environment(opts.envpath)
    from tractags.api import TagSystem

    tlist = opts.tags or split_tags(env.config.get('blog', 'default_tag', 
                                                   'blog'))
    tags = TagSystem(env)
    req = Mock(perm=MockPerm())
    blog = tags.query(req, ' '.join(tlist + ['realm:wiki']))
                   
    cnx = env.get_db_cnx()
    for resource, page_tags in list(blog):
        try:
            page = WikiPage(env, version=1, name=resource.id)
            _, publish_time, author, _, _ =  page.get_history().next()
            if opts.deleteonly:
                page.delete()
                continue
            categories = ' '.join([t for t in page_tags if t not in tlist])
            page = WikiPage(env, name=resource.id)
            for version, version_time, version_author, version_comment, \
                _ in page.get_history():
                # Currently the basename of the post url is used due to 
                # http://trac-hacks.org/ticket/2956
                #name = resource.id.replace('/', '_')
                name = resource.id
                # extract title from text:
                fulltext = page.text
                match = _title_split_match(fulltext)
                if match:
                    title = match.group(1)
                    fulltext = match.group(2)
                else: 
                    title = name
                body = fulltext
                print "Adding post %s, v%s: %s" % (name, version, title)
                insert_blog_post(cnx, name, version, title, body,
                                 publish_time, version_time, 
                                 version_comment, version_author, author,
                                 categories)
                reparent_blog_attachments(env, resource.id, name)
                continue
            cnx.commit()
            if opts.delete:
                page.delete()
                continue
        except:
            env.log.debug("Error loading wiki page %s" % resource.id, 
                          exc_info=True)
            print "Failed to add post %s, v%s: %s" % (name, version, title)
            cnx.rollback()
            cnx.close()
            return 1
    cnx.close()
    return 0
    

def doArgs():
    """Parse command line options"""
    description = "%prog is used to migrate posts from TracBlogPlugin to " \
                  "FullBlogPlugin."

    parser = OptionParser(usage="usage: %prog [options] [environment]",
                          version="1.0", description=description)
    parser.add_option("-d", "--delete", dest="delete", action="store_true",
                      help="Delete the TracBlog posts from the wiki after "
                      "migration", default=False)
    parser.add_option("", "--delete-only", dest="deleteonly", 
                      action="store_true", help="Only delete the TracBlog "
                      "posts from the wiki.  Do not perform any migration "
                      "steps", default=False)
    parser.add_option("-t", "--tags", dest="tags", type="string",
                      help="Comma separated list of tags specifying blog "
                      "posts.  If not specified, the `default_tag` value "
                      "from trac.ini is used.", metavar="<list>",
                      default=None)
    (options, args) = parser.parse_args()
    if len(args) < 1:
        print("You must specify a Trac environment")
        sys.exit(1)
    options.envpath = args[0]
    if not os.path.exists(options.envpath):
        print("The path >%s< does not exist.  Please specify an existing "
              "path." % options.envpath)
        sys.exit(1)
    if options.tags:
        options.tags = options.tags.split(',')
    options.args = args
    return options

if __name__ == '__main__':
    options = doArgs()
    rc = Main(options)
    sys.exit(rc)
