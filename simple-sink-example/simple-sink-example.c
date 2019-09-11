/*
 * Copyright (c) 2019 Francis Deslauriers <francis.deslauriers@efficios.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#include <inttypes.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>

#include <babeltrace2/babeltrace.h>

static bt_graph_simple_sink_component_init_func_status
simple_init_func(bt_self_component_port_input_message_iterator *iterator,
		 void *data)
{
	uint64_t *total_number_event = data;

	*total_number_event = 0;
	return BT_GRAPH_SIMPLE_SINK_COMPONENT_INIT_FUNC_STATUS_OK;
}

static bt_graph_simple_sink_component_consume_func_status
simple_consume_func(bt_self_component_port_input_message_iterator *iterator,
		    void *data)
{
	bt_message_iterator_next_status upstream_iterator_ret_status;
	uint64_t *total_number_event = data;
	bt_message_array_const msgs;
	uint64_t i, count;

	upstream_iterator_ret_status =
		bt_self_component_port_input_message_iterator_next(
			iterator, &msgs, &count);

	if (upstream_iterator_ret_status !=
	    BT_MESSAGE_ITERATOR_NEXT_STATUS_OK) {
		goto end;
	}

	printf("(Received %" PRIu64 " messages.)\n", count);
	for (i = 0; i < count; i++) {
		const bt_message *msg = msgs[i];

		switch (bt_message_get_type(msg)) {
		case BT_MESSAGE_TYPE_EVENT: {
			bt_clock_snapshot_get_ns_from_origin_status status;
			const bt_clock_snapshot *cs;
			int64_t ts;

			cs = bt_message_event_borrow_default_clock_snapshot_const(
				msg);
			status = bt_clock_snapshot_get_ns_from_origin(cs, &ts);
			assert(status ==
			       BT_CLOCK_SNAPSHOT_GET_NS_FROM_ORIGIN_STATUS_OK);

			printf("Event message with timestamp=%" PRIu64 " ns\n",
			       ts);

			*total_number_event += 1;
			break;
		}
		case BT_MESSAGE_TYPE_STREAM_BEGINNING:
			printf("[Stream beginning message]\n");
			break;
		case BT_MESSAGE_TYPE_STREAM_END:
			printf("[Stream end message]\n");
			break;
		case BT_MESSAGE_TYPE_PACKET_BEGINNING:
			printf("[Packet beginning message]\n");
			break;
		case BT_MESSAGE_TYPE_PACKET_END:
			printf("[Packet end message]\n");
			break;
		case BT_MESSAGE_TYPE_DISCARDED_EVENTS:
			printf("[Discarded events message]\n");
			break;
		case BT_MESSAGE_TYPE_DISCARDED_PACKETS:
			printf("[Discarded packets message]\n");
			break;
		case BT_MESSAGE_TYPE_MESSAGE_ITERATOR_INACTIVITY:
			printf("[Message iterator inactivity message]\n");
			break;
		default:
			printf("[Other message type]\n");
		}
		bt_message_put_ref(msg);
	}

end:
	return upstream_iterator_ret_status;
}

static bt_graph *create_graph_with_source(const bt_port_output **out_port)
{
	const bt_component_class_source *src_comp_cls;
	const bt_component_source *src_comp = NULL;
	bt_graph_add_component_status add_comp_status;
	enum bt_plugin_find_all_from_file_status find_all_from_file_status;
	const bt_plugin_set *plugin_set;
	const bt_plugin *text_plugin;
	bt_value *src_params;
	bt_graph *graph;

	/* Find the `dmesg` source component class in the `text` plugin */
	find_all_from_file_status = bt_plugin_find_all_from_file(
		"/usr/local/lib/babeltrace2/plugins/babeltrace-plugin-text.so",
		true, &plugin_set);
	assert(find_all_from_file_status ==
	       BT_PLUGIN_FIND_ALL_FROM_FILE_STATUS_OK);
	assert(bt_plugin_set_get_plugin_count(plugin_set) == 1);

	text_plugin = bt_plugin_set_borrow_plugin_by_index_const(plugin_set, 0);
	src_comp_cls = bt_plugin_borrow_source_component_class_by_name_const(
		text_plugin, "dmesg");

	assert(src_comp_cls);

	/* Create a graph */
	graph = bt_graph_create(0);
	assert(graph);

	/*
	 * Create the initialization parameter for the `src.text.dmesg`
	 * component class. In this case, we want to read from stdin; no
	 * paramter is needed; we pass NULL;
	 */
	src_params = NULL;

	/*
	 * Instantiate a `src.text.dmesg` component from the component class
	 * within the graph.
	 */
	add_comp_status =
		bt_graph_add_source_component(graph, src_comp_cls, "src",
					      src_params, BT_LOGGING_LEVEL_NONE,
					      &src_comp);
	assert(add_comp_status == BT_GRAPH_ADD_COMPONENT_STATUS_OK);
	assert(src_comp);

	/* Get the port object to make the connection later. */
	*out_port = bt_component_source_borrow_output_port_by_index_const(
		src_comp, 0);
	assert(*out_port);

	bt_component_source_put_ref(src_comp);
	bt_plugin_set_put_ref(plugin_set);
	return graph;
}

int main(void)
{
	bt_graph_add_component_status add_comp_status;
	bt_graph_connect_ports_status connect_status;
	const bt_port_output *src_out_port = NULL;
	const bt_component_sink *sink_comp = NULL;
	const bt_port_input *sink_in_port;
	bt_graph_run_status run_status;
	uint64_t total_number_event;
	bt_graph *graph;

	graph = create_graph_with_source(&src_out_port);
	assert(graph);
	assert(src_out_port);

	/*
	 * Instantiate a simple sink component with init and consume callbacks.
	 */
	add_comp_status = bt_graph_add_simple_sink_component(
		graph, "sink", simple_init_func, simple_consume_func, NULL,
		&total_number_event, &sink_comp);
	assert(add_comp_status == BT_GRAPH_ADD_COMPONENT_STATUS_OK);
	assert(sink_comp);

	/*
	 * Make the connection between the source component and the simple
	 * sink.
	 */
	sink_in_port = bt_component_sink_borrow_input_port_by_name_const(
		sink_comp, "in");
	assert(sink_in_port);

	connect_status =
		bt_graph_connect_ports(graph, src_out_port, sink_in_port, NULL);
	assert(connect_status == BT_GRAPH_CONNECT_PORTS_STATUS_OK);

	/* Run the graph until completion. */
	run_status = bt_graph_run(graph);
	assert(run_status == BT_GRAPH_RUN_STATUS_END);

	printf("Total number of events analyzed: %" PRIu64 "\n",
	       total_number_event);

	/* Cleaning up. */
	bt_component_sink_put_ref(sink_comp);
	bt_graph_put_ref(graph);

	return 0;
}
