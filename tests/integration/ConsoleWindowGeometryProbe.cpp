// SPDX-License-Identifier: GPL-3.0-only
// Native Qt/QML window geometry; no capture device or processing graph is opened.
#include "veyra/ui/QmlPlayerBridge.h"
#include "veyra/engine/EngineController.h"
#include <QApplication>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QDir>
#include <QQuickWindow>
#include <QScreen>
#include <QElapsedTimer>
#include <QThread>
#include <cstdio>
#include <memory>
#include <cmath>
#include <filesystem>
int main(int argc,char** argv) {
    QApplication app(argc,argv);if(argc!=2)return 2;
    const std::filesystem::path path=argv[1];if(!path.is_absolute())return 2;
    int failed=0;auto check=[&](bool ok,const char* label){std::printf("%s %s\n",ok?"PASS":"FAIL",label);failed+=!ok;};
    veyra::engine::EngineController engine;
    veyra::ui::QmlPlayerBridge bridge(engine,path);

            bridge.setPreference("autoResume",false);
            check(bridge.setPreference("windowSize","center-video"),"center startup preference accepted");
            const auto settle=[](int ms){QElapsedTimer t;t.start();while(t.elapsed()<ms){QCoreApplication::processEvents();QThread::msleep(5);}};
            for(bool caption : {false,true}) {
                bridge.setPreference("systemTitleBar",caption);
                QQmlEngine qml;qml.addImportPath(QDir(QCoreApplication::applicationDirPath()).filePath("qml"));
                qml.rootContext()->setContextProperty("veyra",&bridge);
                qml.rootContext()->setContextProperty("vySoftwareUi",true);
                qml.rootContext()->setContextProperty("vyTest",QVariantMap{{"reducedMotion",true}});
                QQmlComponent component(&qml,QUrl::fromLocalFile(QDir(QCoreApplication::applicationDirPath()).filePath("qml/Veyra/Main.qml")));
                std::unique_ptr<QObject> ui(component.create());auto* w=ui?qobject_cast<QQuickWindow*>(ui.get()):nullptr;
                if(!w)std::fprintf(stderr,"%s\n",qPrintable(component.errorString()));
                check(w,"actual Main window creates");if(!w)continue;
                settle(800);
                check(ui->property("page").toString()=="min"&&std::abs(w->width()-w->height()*16.0/9)<1.1,"startup automatically selects centered cinema geometry");
                ui->setProperty("page","min");
                check(QMetaObject::invokeMethod(ui.get(),"prepareWindowResize"),"manual resize hands geometry to window manager");
                const QSize manual(1000,std::min(900,w->screen()->availableGeometry().height()-100));
                w->resize(manual);settle(850);
                std::printf("manual caption=%d client=%dx%d\n",caption,w->width(),w->height());
                check(w->size()==manual,"corner resize is not overwritten by cinema aspect binding");
                auto centered=[&](){
                    settle(400);const auto area=w->screen()->availableGeometry(),frame=w->frameGeometry();
                    std::printf("center caption=%d client=%dx%d frame=%d,%d %dx%d area=%d,%d %dx%d\n",caption,w->width(),w->height(),frame.x(),frame.y(),frame.width(),frame.height(),area.x(),area.y(),area.width(),area.height());
                    check(w->visibility()==QWindow::Windowed,"center remains a normal window");
                    check(area.adjusted(-1,-1,1,1).contains(frame),"frame fits work area including native caption");
                    check(std::abs(frame.center().x()-area.center().x())<=1&&std::abs(frame.center().y()-area.center().y())<=1,"window centered on current monitor");
                    check(std::abs(w->width()-w->height()*16.0/9)<1.1,"client preserves 16:9");
                    check(w->height()>=area.height()-w->frameMargins().top()-w->frameMargins().bottom()-1,"uses available height on this ultrawide monitor");
                };
                check(QMetaObject::invokeMethod(ui.get(),"centerVideoWindow"),"center action exists");centered();
                const auto expected=w->geometry();
                check(QMetaObject::invokeMethod(ui.get(),"toggleFullscreen"),"enter fullscreen");settle(300);
                check(QMetaObject::invokeMethod(ui.get(),"toggleFullscreen"),"restore window");settle(400);
                check(w->geometry()==expected,"fullscreen round trip preserves centered rectangle");
                w->showMaximized();settle(300);
                check(QMetaObject::invokeMethod(ui.get(),"centerVideoWindow"),"center from maximized");centered();
                w->close();settle(50);
            }

    check(bridge.setPreference("windowSize","center-video"),"centered startup size accepted and persisted");
    check(bridge.preferences().value("windowSize").toString()=="center-video","centered startup selection accurately exposed");
    return failed?1:0;
}
