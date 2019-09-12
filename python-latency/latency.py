#!/usr/bin/env python3
#
# Copyright (c) 2019 Francis Deslauriers <francis.deslauriers@efficios.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import bt2
import sys


def main():
    if len(sys.argv) != 2:
        print("Need one LTTng kernel trace")
        sys.exit(-1)

    # LTTng kernel trace with 'block_rq_insert' and 'block_rq_complete' events.
    msg_iter = bt2.TraceCollectionMessageIterator(sys.argv[1])

    requests = {}

    for msg in msg_iter:
        if type(msg) is not bt2._EventMessageConst:
            continue

        if msg.event.name == "block_rq_insert":
            request_id = (msg.event["dev"], msg.event["sector"])

            # Save the insertion time and the issuing program name.
            requests[request_id] = (
                msg.default_clock_snapshot.ns_from_origin,
                msg.event["comm"],
            )
        elif msg.event.name == "block_rq_complete":

            request_id = (msg.event["dev"], msg.event["sector"])
            try:
                # Get the request insertion time and the issuing program name.
                start_time, comm = requests[request_id]
            except KeyError:
                # We did not record the issuing of this request.
                continue

            print(
                "[{}] Block request took {} ns".format(
                    comm, msg.default_clock_snapshot.ns_from_origin - start_time
                )
            )


if __name__ == "__main__":
    main()
