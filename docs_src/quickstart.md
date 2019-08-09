# heapprof quickstart

You can install heapprof by running

`pip install heapprof`

The simplest way to get a heap profile for your program is to run

`python -m heapprof -o <filename> -- mycommand.py args...`

This will run your command and write the output to the files `<filename>.hpm` and `<filename>.hpd`.
(Collectively, the "hpx files") Alternatively, you can control heapprof programmatically:

```
import heapprof

heapprof.start('filename')
... do something ...
heapprof.stop()
```

You can analyze hpx files with the analysis and visualization tools built in to heapprof, or use its
APIs to dive deeper into your program's memory usage yourself. For example, you might do this with
the built-in visualization tools:

```
import heapprof
r = heapprof.read('filename')

# Generate a plot of total memory usage over time. This command requires that you first pip install
# matplotlib.
r.timePlot().pyplot()

# Looks like something interested happened 300 seconds in. You can look at the output as a Flame
# graph and view it in a tool like speedscope.app.
r.writeFlameGraph('flame-300.txt', 300)

# Or you can look at the output as a Flow graph and view it using graphviz. (See graphviz.org)
r.flowGraphAt(300).asDotFile('300.dot')

# Maybe you'd like to compare three times and see how memory changed. This produces a multi-time
# Flow graph.
r.compare('compare.dot', r.flowGraphAt(240), r.flowGraphAt(300), r.flowGraphAt(500))

# Or maybe you found some lines of code where memory use seemed to shift interestingly.
r.timePlot({
  'read_data': '/home/wombat/myproject/io.py:361',
  'write_buffer': '/home/wombat/myproject/io.py:582',
})
```

One thing you'll notice in the above is that visualization tools require you to install extra
packages -- that's a way to keep heapprof's dependencies down.

To learn more, continue on to [Using heapprof](using_heapprof.md)
