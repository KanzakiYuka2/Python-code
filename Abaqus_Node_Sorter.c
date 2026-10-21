#include <stdio.h>
#include <string.h>

//最大節点数を設定
#define MAXNODE 10000
//一行あたりの最大文字数
#define MAXLINE 256

//節点情報を格納
struct _nodeData {
    int data_num[MAXNODE];
    double data_x[MAXNODE];
    double data_y[MAXNODE];
    double data_z[MAXNODE];
}d;

//キーワードが検出されるまでファイルポインタを進める
//1行最大256文字まで
int SearchKeyword(FILE *fpo, FILE *fpw, char *Key) {
    char getLine[MAXLINE];

    while(fgets(getLine, sizeof(getLine), fpo) != NULL) {
        fprintf(fpw, "%s", getLine);

        //キーワードを検出したらループを抜ける
        if(strstr(getLine, Key) != NULL) {
            break;
        }
    }
    return 0;
}

//x・y・zの順に並べ替え(バブルソート)
int Sort(int nodeNumber) {
    //x軸方向にソート
    for(int i = 0; i < nodeNumber; i++) {
        for(int j = nodeNumber - 1; j > i; j--) {
            if(d.data_x[j] < d.data_x[j-1]) {
                int dtemp;
                double temp;

                //節点番号をスワップ
                dtemp = d.data_num[j];
                d.data_num[j] = d.data_num[j-1];
                d.data_num[j-1] = dtemp;

                //x座標をスワップ
                temp = d.data_x[j];
                d.data_x[j] = d.data_x[j-1];
                d.data_x[j-1] = temp;

                //y座標をスワップ
                temp = d.data_y[j];
                d.data_y[j] = d.data_y[j-1];
                d.data_y[j-1] = temp;

                //z座標をスワップ
                temp = d.data_z[j];
                d.data_z[j] = d.data_z[j-1];
                d.data_z[j-1] = temp;
            }
        }
    }
    //y軸方向にソート
    for(int i = 0; i < nodeNumber; i++) {
        for(int j = nodeNumber - 1; j > i; j--) {
            if(d.data_y[j] < d.data_y[j-1] && d.data_x[j] <= d.data_x[j-1]) {
                int dtemp;
                double temp;

                //節点番号をスワップ
                dtemp = d.data_num[j];
                d.data_num[j] = d.data_num[j-1];
                d.data_num[j-1] = dtemp;

                //x座標をスワップ
                temp = d.data_x[j];
                d.data_x[j] = d.data_x[j-1];
                d.data_x[j-1] = temp;

                //y座標をスワップ
                temp = d.data_y[j];
                d.data_y[j] = d.data_y[j-1];
                d.data_y[j-1] = temp;

                //z座標をスワップ
                temp = d.data_z[j];
                d.data_z[j] = d.data_z[j-1];
                d.data_z[j-1] = temp;
            }
        }
    }
    //z軸方向にソート
    for(int i = 0; i < nodeNumber; i++) {
        for(int j = nodeNumber - 1; j > i; j--) {
            if(d.data_z[j] < d.data_z[j-1] && d.data_x[j] <= d.data_x[j-1] && d.data_y[j] <= d.data_y[j-1]) {
                int dtemp;
                double temp;

                //節点番号をスワップ
                dtemp = d.data_num[j];
                d.data_num[j] = d.data_num[j-1];
                d.data_num[j-1] = dtemp;

                //x座標をスワップ
                temp = d.data_x[j];
                d.data_x[j] = d.data_x[j-1];
                d.data_x[j-1] = temp;

                //y座標をスワップ
                temp = d.data_y[j];
                d.data_y[j] = d.data_y[j-1];
                d.data_y[j-1] = temp;

                //z座標をスワップ
                temp = d.data_z[j];
                d.data_z[j] = d.data_z[j-1];
                d.data_z[j-1] = temp;
            }
        }
    }
    return 0;
}

//節点番号を取得し，ソート後書き込み
int NodeSort(FILE *fpo, FILE *fpw) {
    int lp = 0;

    //節点番号・座標データ取得
    printf("(節点情報取得) 節点情報インポート中…");
    while(fscanf(fpo, "%d,%lf,%lf,%lf", &d.data_num[lp], &d.data_x[lp], &d.data_y[lp], &d.data_z[lp]) == 4) {
        lp++;
    }
    printf("%d節点を検出しました\n\n", lp);

    printf("(節点再割当) 節点スワップ中…");
    Sort(lp);
    printf("完了\n\n");

    for(int i = 0; i < lp; i++) {
        fprintf(fpw, "%d,%lf,%lf,%lf\n", i + 1, d.data_x[i], d.data_y[i], d.data_z[i]);
    } 

    return lp;
}

//節点集合の節点番号書き換え
int SetNodeRenumber(FILE *fpo, FILE *fpw, int lp) {
    int elementNode[lp];
    int rp = 0;
    int gt = 0;
    printf("(*Nset) 節点番号書き換え中…");
    //節点情報取得
    while(1) {
        int num = fscanf(fpo, "%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d", &elementNode[16*rp], &elementNode[16*rp+1], &elementNode[16*rp+2], &elementNode[16*rp+3], &elementNode[16*rp+4], &elementNode[16*rp+5], &elementNode[16*rp+6], &elementNode[16*rp+7], &elementNode[16*rp+8], &elementNode[16*rp+9], &elementNode[16*rp+10], &elementNode[16*rp+11], &elementNode[16*rp+12], &elementNode[16*rp+13], &elementNode[16*rp+14], &elementNode[16*rp+15]);
        
        rp++;
        gt += num;
        //何も数値を読み込めなかった場合
        if(num == 0) {
            break;
        }
    }

    //節点番号の参照と入替え
    for(int i = 0; i < gt; i++) {
        int p;
        for(int j = 0; j < lp; j++) {
            if(elementNode[i] == d.data_num[j]) {
                p = j + 1;
            }
        }
        elementNode[i] = p;
    }

    //節点番号の昇順ソート
    for(int i = 0; i < gt; i++) {
        for(int j = gt - 1; j > i; j--) {
            if(elementNode[j] < elementNode[j-1]) {
                int temp = elementNode[j];
                elementNode[j] = elementNode[j-1];
                elementNode[j-1] = temp;
            }
        }
    }

    //ファイルへの書き込み
    rp = 0;
    for(int i = 0; i < gt; i++) {
        fprintf(fpw, "%d", elementNode[i]);
        rp++;
        if(rp >= 16 || i == gt - 1) {
            rp = 0;
            fprintf(fpw, "\n");
        }
        else {
            fprintf(fpw, ",");
        }

    }
    
    printf("完了\n");

    return 0;
}

//8頂点要素のみ対応
//要素の節点番号書き換え
int ElementNodeRenumber(FILE *fpo, FILE *fpw, int lp) {
    int elementNode[9];

    printf("(*Element) 節点番号書き換え中…");
    while(fscanf(fpo, "%d,%d,%d,%d,%d,%d,%d,%d,%d", &elementNode[0], &elementNode[1], &elementNode[2], &elementNode[3], &elementNode[4], &elementNode[5], &elementNode[6], &elementNode[7], &elementNode[8]) == 9) {
        //節点番号参照と入替え
        for(int i = 1; i < 9; i++) {
            int p;
            for(int j = 0; j < lp; j++) {
                if(elementNode[i] == d.data_num[j]) {
                    p = j + 1;
                }
            }
            elementNode[i] = p;
        }
        //情報を出力
        fprintf(fpw, "%d,%d,%d,%d,%d,%d,%d,%d,%d\n", elementNode[0], elementNode[1], elementNode[2], elementNode[3], elementNode[4], elementNode[5], elementNode[6], elementNode[7], elementNode[8]);
    }
    printf("完了\n");

    return 0;
}

//Element，*Nsetの数を数える
int SearchCount(FILE *fpo, int *Nelement, int *Nset) {
    char getLine[MAXLINE];
    *Nelement = 0;
    *Nset = 0;

    while(fgets(getLine, sizeof(getLine), fpo) != NULL) {
        //キーワードを検出したらカウントを増やす
        if(strstr(getLine, "*Element") != NULL && strstr(getLine, "type") != NULL) {
            *Nelement = *Nelement + 1;
        }
    }

    //ファイルポインタを先頭に戻す
    if(fseek(fpo, 0, SEEK_SET) != 0) {
        return -1;
    }

    while(fgets(getLine, sizeof(getLine), fpo) != NULL) {
        //キーワードを検出したらカウントを増やす
        if(strstr(getLine, "*Nset") != NULL) {
            *Nset = *Nset + 1;
        }
    }

    //ファイルポインタを先頭に戻す
    if(fseek(fpo, 0, SEEK_SET) != 0) {
        return -1;
    }

    return 0;
}

int main(int argc, char *argv[]) {
    FILE *fpo;  //読込用
    FILE *fpw;  //書出用
    int lp = 0; //節点数
    char dest[50] = {'r', 'e', '_'};//出力文字

    int Nelement;   //要素の種類数(*Elementヘッダの数)
    int Nset;       //集合の数(*Nsetの数)(要素番号は変更せず，節点番号のみ変更したため，*Elsetは不必要)

    printf("【Abaqus節点番号再割当ツール(ver.2021/6/9)】\n\n");

    if (argc < 2) {
        printf("(異常終了) コマンドラインにファイルを指定してください\n");
        return -1;
    } 
    else if(argc > 2) {
        printf("(異常終了) コマンドラインで読み込めるファイルは1つだけです\n");
        return -1;
    }

    //ファイルオープン処理
    if ((fpo = fopen(argv[1], "r")) == NULL) {
        printf("(異常終了) 読み込みエラーです\n");
        return -1;
    }

    strcat(dest, argv[1]);

    if ((fpw = fopen(dest, "w")) == NULL) {
        printf("(異常終了) 書き込みエラーです\n");
        return -1;
    }
    printf("(出力ファイル) %s\n\n", dest);

    //*Element・*Nsetの数をカウントし，その後，ファイルポインタを先頭に戻す
    if (SearchCount(fpo, &Nelement, &Nset) == -1) {
        printf("(異常終了) ファイルポインタを先頭に戻せませんでした\n");
        return -1;
    }
    printf("(ラベル検出) [*Element : %d個] [*Nset : %d個] 検出しました\n\n", Nelement, Nset);

    //*Nodeヘッダを検出するまで書き込む
    SearchKeyword(fpo, fpw, "*Node");
    //節点番号・座標データを取得し，座標ごとに降順に並べかえ，書き込む
        SearchKeyword(fpo, fpw, "*Element");
        //要素の節点番号を書き換える
        ElementNodeRenumber(fpo, fpw, lp);
    }

    printf("\n");

    //*Nsetヘッダ処理
    for(int i = 0; i < Nset; i++) {
        SearchKeyword(fpo, fpw, "*Nset");
        //要素の節点番号を書き換える
        SetNodeRenumber(fpo, fpw, lp);
    }

    SearchKeyword(fpo, fpw, "絶対に一致しない文字列");

    //ファイルクローズ処理
    fclose(fpo);
    fclose(fpw);

    printf("\n(正常終了) 再割当て完了しました\n");

    return 0;
}