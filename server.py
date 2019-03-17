from flask import Flask, send_from_directory

app = Flask(__name__)


@app.route('/dist/<path:path>')
def send_js(path):
    return send_from_directory('dist', path)


def homepage() -> str:
    return """
<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8" />
    <title>Hello World</title>
    <style>
    #root {
        display: flex;
        justify-content: space-between;
    }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <!--
      Note: this page is a great way to try React but it's not suitable for production.
      It slowly compiles JSX with Babel in the browser and uses a large development build of React.

      Read this section for a production-ready setup with JSX:
      https://reactjs.org/docs/add-react-to-a-website.html#add-jsx-to-a-project

      In a larger project, you can use an integrated toolchain that includes JSX instead:
      https://reactjs.org/docs/create-a-new-react-app.html

      You can also use React without JSX, in which case you can remove Babel:
      https://reactjs.org/docs/react-without-jsx.html
    -->
    <script src="dist/main.js"></script>

  </body>
</html>

"""


@app.route("/")
def home():
    return homepage()


if __name__ == "__main__":
    app.run()
