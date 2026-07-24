$(function(){
    
    function verifying() {
        $(".drag-refresh-bg").css("display", "block");
    }

    function verifyFailed() {
        $(".drag-slide-message").addClass("error-message")
        $(".drag-slide-message").text("验证失败，请重试")
        $(".drag-slide-message").css("display", "block")
        setTimeout(function() {
            initCaptcha()
        }, 1000)
    }

    function verifySuccess() {
        $(".drag-slide-message").addClass("succes-message")
        $(".drag-slide-message").text("验证成功")
        $(".drag-slide-message").css("display", "block")

        setTimeout(function () {
            layer.close(layer.index)
            $("button#login").click();
        }, 1000)
    }

    // function refreshCaptcha() {
    //     $.get("/login/image", function(data){
    //         $(".drag-float__image img").attr("src", data.p)
    //         $(".drag-float__btn img").attr("src", data.s)
    //         $(".drag-float__btn").css("top", data.h)
    //     })
    //     $(".drag-float__verify").css("display", "none")
    //     $(".drag-float__success").css("display", "none")
    //     $(".drag-float__failed").css("display", "none")
    //     $(".drag-float").css("display", "none")
    //     $(".drag-btn").css("left", "0px")
    //     $(".drag-float__btn").css("left", "0px")
    //     $(".drag-bg").css("width", "0px")
    // }

    function start(e) {
        status = true
        if (!e.originalEvent || !e.originalEvent.touches) {
            downX = e.clientX
            locations.push({x: e.clientX, y: e.clientY})
        } else {
            downX = e.originalEvent.touches[0].pageX
            locations.push({x: e.originalEvent.touches[0].pageX, y: e.originalEvent.touches[0].pageY})
        }
        distance = $(".drag-captcha-footer")[0].offsetWidth - btn.offsetWidth
        $(".drag-captcha-slidebar-tip").css("color", "#eaeaea")
    }

    function move(e) {
        if (status) {
            if (!e.touches) {
                var x = e.clientX
            } else {
                var x = e.touches[0].pageX
            }

            
            var offset = x - downX
            if (offset > distance) {
                offset = distance
            } else if (offset < 0) {
                offset = 0
            }

            movedWidth = offset
            $(".drap-captcha-slidetrigger").css("left", offset + 10 + "px")
            $(".drag-slide-identity").css("left", offset + 10 + "px")
        }
    }

    function end(e) {
        if (status) {
            status = false
            if (!e.originalEvent || !e.originalEvent.touches) {
                downX = e.clientX
                locations.push({x: e.clientX, y: e.clientY})
            } else {
                downX = e.originalEvent.touches[0].pageX
                locations.push({x: e.originalEvent.touches[0].pageX, y: e.originalEvent.touches[0].pageY})
            }
            $(".drag-captcha-slidebar-tip").css("color", "rgba(141,142,146,0.87)")
            verifying()
            var verifyRequest = $.post(
                "/login/verify",
                {
                    w: movedWidth,
                    t: endTime - startTime,
                    locations: locations
                })
            verifyRequest.done(function(data) {
                if (data.success) {
                    verifySuccess()
                } else {
                    verifyFailed()
                }
            })
            verifyRequest.fail(function(error) {
                console.log(error)
                verifyFailed()
            })
        }
    }

    var floatBtn = $("#drag-captcha-bg")[0]
    var btn = $("#drap-captcha-slidetrigger")[0]
    var distance = $(".drag-captcha-footer")[0].offsetWidth - btn.offsetWidth
    var downX = 0
    var status = false

    var captchaLoading = false

    // 滑动的指标
    // 1.距离
    var movedWidth = 0
    // 2.时间
    var startTime = 0
    var endTime = 0
    // 3.路径
    var locations = []

    $(btn).on('mousedown', function(e){
        start(e)
        document.addEventListener("mousemove", function(e){
            move(e)
        })
        document.addEventListener("mouseup", function(e) {
            end(e)
        })
    })
    $(btn).on('touchstart', function(e){
        start(e)
        document.addEventListener("touchmove", function(e){
            move(e)
        })
        document.addEventListener("touchend", function(e) {
            end(e)
        })
    })

    // $(".drag-float__failed svg").on("click", function(){
    //     refreshCaptcha()
    // })
});