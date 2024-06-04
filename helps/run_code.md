# 代码运行服务 (run_code)

基于 glot.io 提供代码运行服务


###  指令列表

- [`/code` 运行代码](#code)

---


## `/code`

指定语言和标准输入运行代码，返回标准输出。支持语言：
`py/php/java/cpp/js/c#/c/go/asm/ats/bash/clisp/clojure/cobol/coffeescript/crystal/d/elixir/elm/erlang/fsharp/groovy/guide/hare/haskell/idris/julia/kotlin/lua/mercury/nim/nix/ocaml/pascal/perl/raku/ruby/rust/sac/scala/swift/typescript/zig/plaintext`

- **使用方式**

    ```
    /code <语言> <输入>
    <代码>
    ```

- **示例**

    ```
    /code py 1 2
    a, b = map(int, input().split())
    print(a + b)
    ```