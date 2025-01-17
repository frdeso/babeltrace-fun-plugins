import bt2
import cantools
import struct

bt2.register_plugin(
    module_name=__name__,
    name="can",
    description="CAN Format",
    author="Gabriel-Andrew Pollo-Guilbert",
    license="GPL",
    version=(1, 0, 0),
)


def log_info(cur_log_level):
    return cur_log_level <= bt2.LoggingLevel.INFO


def print_info(text):
    print("INFO: {}".format(text))


class CANIterator(bt2._UserMessageIterator):
    def __init__(self, port):
        path, trace_class, self._messages = port.user_data
        self._file = open(path, "rb")

        trace = trace_class()

        stream_class = trace_class[0]
        self._stream = trace.create_stream(stream_class)
        self._init_msgs = [self._create_stream_beginning_message(self._stream)]
        self._end_msgs = [self._create_stream_end_message(self._stream)]

        self._next = self._next_init

    def _create_decoded_event(self, timestamp, frame_id, bytedata):
        if len(self._messages[frame_id]) == 2:
            (database, event_class) = self._messages[frame_id]
            decoded_data = database.decode_message(frame_id, bytedata)
        elif len(self._messages[frame_id]) == 3:
            (database, event_classes, key) = self._messages[frame_id]
            decoded_data = database.decode_message(frame_id, bytedata)
            event_class = event_classes[decoded_data[key]]
        else:
            raise ValueError

        event_msg = self._create_event_message(
            event_class, self._stream, default_clock_snapshot=timestamp
        )

        for key in event_msg.event.payload_field.keys():
            event_msg.event.payload_field[key] = decoded_data[key]

        return event_msg

    def _create_unknown_event(self, timestamp, frame_id, bytedata):
        event_class = self._messages[None]

        event_msg = self._create_event_message(
            event_class, self._stream, default_clock_snapshot=timestamp
        )

        event_msg.event.payload_field["id"] = frame_id
        for i in range(7):
            event_msg.event.payload_field[f"byte {i}"] = bytedata[i]

        return event_msg

    def _next_init(self):
        if len(self._init_msgs) > 0:
            return self._init_msgs.pop(0)
        else:
            self._next = self._next_events
            return self._next()

    def _next_events(self):
        # Custom binary format parsing.
        #
        # [bytes 0 -  3] timestamp
        # [bytes 4 -  7] frame ID (standard or extended)
        # [bytes 8 - 15] up to 64 bits of data

        msg = self._file.read(16)
        if msg == b"":
            self._next = self._next_end
            return self._next()

        timestamp, frame_id, data = struct.unpack("<ii8s", msg)

        if frame_id in self._messages:
            event_msg = self._create_decoded_event(timestamp, frame_id, data)
        else:
            event_msg = self._create_unknown_event(timestamp, frame_id, data)

        return event_msg

    def _next_end(self):
        if len(self._end_msgs) > 0:
            return self._end_msgs.pop(0)
        else:
            raise StopIteration

    def __next__(self):
        return self._next()


@bt2.plugin_component_class
class CANSource(bt2._UserSourceComponent, message_iterator_class=CANIterator):
    def __init__(self, params, obj):
        inputs = CANSource._get_param_list(params, "inputs")
        databases = CANSource._get_param_list(params, "databases")

        (trace_class, messages) = self._create_trace_class_for_databases(databases)

        for path in inputs:
            self._create_port_for_can_trace(trace_class, messages, str(path))

    def _create_trace_class_for_databases(self, databases):
        messages = dict()
        clock_class = self._create_clock_class(frequency=1000)
        trace_class = self._create_trace_class()
        stream_class = trace_class.create_stream_class(
            name="can", default_clock_class=clock_class
        )

        if log_info(self.logging_level):
            print_info(f"created trace class {trace_class}")

        event_class = CANSource._create_unknown_event_class(trace_class, stream_class)
        messages[None] = event_class

        if log_info(self.logging_level):
            print_info(f"created event class 'UNKNOWN' at {event_class}")

        for path in databases:
            self._create_database_event_classes(
                trace_class, stream_class, str(path), messages
            )

        return (trace_class, messages)

    def _create_port_for_can_trace(self, trace_class, messages, path):
        self._add_output_port(path, (path, trace_class, messages))

    @staticmethod
    def _get_param_list(params, key):
        if key not in params:
            raise ValueError(f"missing `{key}` parameter")
        param = params[key]

        if type(param) != bt2.ArrayValue:
            raise TypeError(
                f"expecting `{key}` parameter to be a list, got a {type(param)}"
            )

        if len(param) == 0:
            raise ValueError(f"expecting `{key}` to not be of length zero")

        return param

    def _create_database_event_classes(self, trace_class, stream_class, path, messages):
        try:
            database = cantools.db.load_file(path)
        except FileNotFoundError as err:
            raise ValueError(f"database file `{path}` couldn't be read.") from err

        for message in database.messages:
            if message.frame_id in messages:
                if log_info(self.logging_level):
                    print_info(f"{message.name} already present in another database")

                continue

            multiplexed = False
            for signal in message.signal_tree:
                if isinstance(signal, str):
                    continue
                multiplexed = True
                break

            if multiplexed:
                (event_classes, key) = CANSource._create_multiplexed_message_classes(
                    trace_class, stream_class, message
                )
                messages[message.frame_id] = [database, event_classes, key]
                if log_info(self.logging_level):
                    print_info(f"created event class '{message.name}' at {event_class}")
            else:
                event_class = CANSource._create_message_class(
                    trace_class, stream_class, message
                )
                messages[message.frame_id] = [database, event_class]
                if log_info(self.logging_level):
                    print_info(f"created event class '{message.name}' at {event_class}")

    @staticmethod
    def _create_unknown_event_class(trace_class, stream_class):
        field_class = trace_class.create_structure_field_class()
        field_class.append_member("id", trace_class.create_real_field_class())
        for i in range(8):
            field_class.append_member(
                f"byte {i}", trace_class.create_real_field_class()
            )

        event_class = stream_class.create_event_class(
            name="UNKNOWN", payload_field_class=field_class
        )

        return event_class

    @staticmethod
    def _create_multiplexed_message_classes(trace_class, stream_class, message):
        event_classes = dict()

        multiplexer = None
        signals = []
        for signal in message.signal_tree:
            if isinstance(signal, str):
                signals.append(signal)
            elif multiplexer is None:
                multiplexer = signal
            else:
                raise ValueError(f"multiple multiplexer in message `{message.name}`")

        if multiplexer is None or len(multiplexer) == 0:
            raise ValueError(f"no multiplexer found in `{message.name}`")

        if len(multiplexer) > 1:
            raise ValueError(f"more than 1 multiplexer found in `{message.name}`")

        key = list(multiplexer.keys())[0]
        for value in sorted(multiplexer[key].keys()):
            field_class = trace_class.create_structure_field_class()
            field_class.append_member(key, trace_class.create_real_field_class())
            for signal in multiplexer[key][value]:
                field_class.append_member(signal, trace_class.create_real_field_class())
            for signal in signals:
                field_class.append_member(signal, trace_class.create_real_field_class())

            event_class = stream_class.create_event_class(
                name=message.name, payload_field_class=field_class
            )
            event_classes[value] = event_class

        return (event_classes, key)

    @staticmethod
    def _create_message_class(trace_class, stream_class, message):
        field_class = trace_class.create_structure_field_class()

        def _by_start_bit(sig):
            return sig.start

        for signal in sorted(message.signals, key=_by_start_bit):
            field_class.append_member(
                signal.name, trace_class.create_real_field_class()
            )

        event_class = stream_class.create_event_class(
            name=message.name, payload_field_class=field_class
        )

        return event_class
