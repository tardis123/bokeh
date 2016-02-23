from __future__ import absolute_import, print_function

import os
import pytest
import requests
import subprocess
import sys
import time

from bokeh.io import output_file
from os.path import join, exists, dirname, pardir
from requests.exceptions import ConnectionError

from tests.utils.constants import default_upload
from tests.utils.utils import write, upload_file_to_s3
from tests.utils.webserver import SimpleWebServer

pytest_plugins = "tests.examples.examples_report_plugin"


def pytest_addoption(parser):
    parser.addoption(
        "--upload", dest="upload", action="store_true", default=default_upload, help="upload test artefacts to S3"
    )
    parser.addoption(
        "--log-file", dest="log_file", metavar="path", action="store", default='examples.log', help="where to write the complete log"
    )
    parser.addoption(
        "--bokeh-port", dest="bokeh_port", type=int, default=5006, help="port on which Bokeh server resides"
    )
    parser.addoption(
        "--notebook-port", type=int, default=6007, help="port on which Jupyter Notebook server resides"
    )
    parser.addoption(
        "--all-notebooks", action="store_true", default=False, help="test all the notebooks inside examples/plotting/notebook folder."
    )
    parser.addoption(
        "--output-cells", type=str, choices=['complain', 'remove', 'ignore'], default='complain', help="what to do with notebooks' output cells"
    )


def pytest_sessionfinish(session, exitstatus):
    try_upload = session.config.option.upload
    seleniumreport = session.config.option.htmlpath
    if try_upload and seleniumreport:
        upload_file_to_s3(seleniumreport)


@pytest.yield_fixture(scope="session")
def log_file():
    with open(pytest.config.option.log_file, 'w') as f:
        yield f


@pytest.fixture
def selenium(selenium):
    # Give items a chance to load
    selenium.implicitly_wait(10)
    selenium.set_window_size(width=600, height=600)
    return selenium


@pytest.fixture(scope='session')
def file_server(request):
    server = SimpleWebServer()
    server.start()
    request.addfinalizer(server.stop)
    return server


@pytest.fixture(scope='session')
def base_url(request, file_server):
    return 'http://%s:%s' % (file_server.host, file_server.port)


@pytest.fixture
def output_file_url(request, base_url):

    filename = request.function.__name__ + '.html'
    file_obj = request.fspath.dirpath().join(filename)
    file_path = file_obj.strpath

    output_file(file_path, mode='inline')

    def tearDown():
        if file_obj.isfile():
            file_obj.remove()
    request.addfinalizer(tearDown)

    return '%s/%s' % (base_url, file_path)


@pytest.fixture(scope="session")
def capabilities(capabilities):
    capabilities["browserName"] = "firefox"
    capabilities["tunnel-identifier"] = os.environ.get("TRAVIS_JOB_NUMBER")
    return capabilities


@pytest.fixture(scope='session')
def bokeh_server(request, log_file):
    bokeh_port = pytest.config.option.bokeh_port

    cmd = ["bin/bokeh", "serve"]
    argv = ["--port=%s" % bokeh_port]
    bokeh_server_url = 'http://localhost:%s' % bokeh_port

    try:
        proc = subprocess.Popen(cmd + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        write("Failed to run: %s" % " ".join(cmd + argv))
        sys.exit(1)
    else:
        # Add in the clean-up code
        def stop_bokeh_server():
            write("Shutting down bokeh-server ...")
            proc.kill()
        request.addfinalizer(stop_bokeh_server)

        def wait_until(func, timeout=5.0, interval=0.01):
            start = time.time()

            while True:
                if func():
                    return True
                if time.time() - start > timeout:
                    return False
                time.sleep(interval)

        def wait_for_bokeh_server():
            def helper():
                if proc.returncode is not None:
                    return True
                try:
                    return requests.get(bokeh_server_url)
                except ConnectionError:
                    return False

            return wait_until(helper)

        if not wait_for_bokeh_server():
            write("Timeout when running: %s" % " ".join(cmd + argv))
            sys.exit(1)

        if proc.returncode is not None:
            write("bokeh server exited with code " + str(proc.returncode))
            sys.exit(1)

        return bokeh_server_url


@pytest.fixture(scope="session")
def jupyter_notebook(request, bokeh_server, log_file):
    # First - set-up the notebooks to run all cells when they're opened
    #
    # Can be cleaned up further to remember the user's existing customJS
    # and then restore it after the test run.
    from jupyter_core import paths
    config_dir = paths.jupyter_config_dir()

    body = """
require(["base/js/namespace", "base/js/events"], function (IPython, events) {
    events.on("kernel_ready.Kernel", function () {
        IPython.notebook.execute_all_cells();
    });
});
"""
    custom = join(config_dir, "custom")
    if not exists(custom):
        os.makedirs(custom)

    customjs = join(custom, "custom.js")
    with open(customjs, "w") as f:
        f.write(body)

    # Add in the clean-up code
    def clean_up_customjs():
        with open(customjs, "w") as f:
            f.write("")

    request.addfinalizer(clean_up_customjs)

    # Second - Run a notebook server at the examples directory
    #

    notebook_port = pytest.config.option.notebook_port

    env = os.environ.copy()
    env['BOKEH_RESOURCES'] = 'server'

    notebook_dir = join(dirname(__file__), pardir)

    cmd = ["jupyter", "notebook"]
    argv = ["--no-browser", "--port=%s" % notebook_port, "--notebook-dir=%s" % notebook_dir]
    jupter_notebook_url = "http://localhost:%d" % notebook_port

    try:
        proc = subprocess.Popen(cmd + argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        write("Failed to run: %s" % " ".join(cmd + argv))
        sys.exit(1)
    else:
        # Add in the clean-up code
        def stop_jupyter_notebook():
            write("Shutting down jupyter-notebook ...")
            proc.kill()

        request.addfinalizer(stop_jupyter_notebook)

        def wait_until(func, timeout=5.0, interval=0.01):
            start = time.time()

            while True:
                if func():
                    return True
                if time.time() - start > timeout:
                    return False
                time.sleep(interval)

        def wait_for_jupyter_notebook():
            def helper():
                if proc.returncode is not None:
                    return True
                try:
                    return requests.get(jupter_notebook_url)
                except ConnectionError:
                    return False

            return wait_until(helper)

        if not wait_for_jupyter_notebook():
            write("Timeout when running: %s" % " ".join(cmd + argv))
            sys.exit(1)

        if proc.returncode is not None:
            write("Jupyter notebook exited with code " + str(proc.returncode))
            sys.exit(1)

        return jupter_notebook_url
