from flask import Flask

import config


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)

    # 注册蓝图路由
    from routes.gallery import gallery_bp
    from routes.admin import admin_bp
    from routes.forensics import forensics_bp
    # from routes.robustness import robustness_bp

    app.register_blueprint(gallery_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(forensics_bp)
    # app.register_blueprint(robustness_bp)

    return app
