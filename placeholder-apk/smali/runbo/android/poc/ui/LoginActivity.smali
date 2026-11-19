.class public Lrunbo/android/poc/ui/LoginActivity;
.super Landroid/app/Activity;
.source "LoginActivity.java"


# direct methods
.method public constructor <init>()V
    .registers 1

    invoke-direct {p0}, Landroid/app/Activity;-><init>()V

    return-void
.end method


# virtual methods
.method protected onCreate(Landroid/os/Bundle;)V
    .registers 2

    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    # 占位页：仅用于让定制的开机恢复流程不抛异常，立即关闭
    invoke-virtual {p0}, Lrunbo/android/poc/ui/LoginActivity;->finish()V

    return-void
.end method
