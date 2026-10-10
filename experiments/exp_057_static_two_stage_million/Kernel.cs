using System;
using System.IO;
using System.Collections.Generic;

public static class Adc057 {
    public static ulong Mix(ulong x) {
        unchecked { x=(x^(x>>30))*0xBF58476D1CE4E5B9UL; x=(x^(x>>27))*0x94D049BB133111EBUL; }
        return x^(x>>31);
    }
    public static ulong Word(ulong seed, int stream, long index) {
        unchecked { return Mix(seed ^ ((ulong)stream*0xD1B54A32D192ED03UL) ^ ((ulong)index*0x9E3779B97F4A7C15UL)); }
    }
    public static double Input(ulong seed,long index) { return -0.82+1.64*(Word(seed,1,index)>>11)*(1.0/9007199254740992.0); }
    public static int Tag(ulong seed,int stream,long index) { return (Word(seed,stream,index)>>63)==0?-1:1; }
    public static int Flash(double x) {
        int q=-4;
        for(int i=0;i<8;i++) if(x>=-0.875+i*0.25)q++;
        return q;
    }
    public static double Quantize(double r) { return Math.Min(Math.Max(Math.Floor((r+1)*128)-128,-128),127); }
    public static bool Gate(int j,double local,double threshold) { return j==0||Math.Abs(local)>=threshold; }
    public static double[] Plant(double x,int d1,int d2,double a1,double b1,double a2,double b2) {
        int q1=Flash(x);
        double z1=4*(x-q1/4.0+d1/32.0);
        double r1=b1==0?a1*z1:a1*z1+b1*Math.Pow(z1,3);
        int q2=Flash(r1);
        double z2=4*(r1-q2/4.0+d2/32.0);
        double r2=b2==0?a2*z2:a2*z2+b2*Math.Pow(z2,3);
        return new double[]{q1,q2,r1,r2,128*r2,Quantize(r2)};
    }
    public static double Pwl(double raw,double[] k,int offset,double width) {
        double domain=4*width;
        if(raw < -domain || raw>=domain || Double.IsNaN(raw)) throw new Exception("invalid PWL raw domain");
        double mag=Math.Abs(raw);
        int slice=Math.Min((int)(mag/width),3);
        double v=0;
        for(int j=0;j<slice;j++)v+=width*k[offset+j];
        v+=k[offset+slice]*(mag-slice*width);
        return raw<0?-v:(raw==0?0:v);
    }
    // Digital-only correction: no X, a, b, training targets, or oracle.
    public static double[] Correct(int q1,int q2,double backend,int d1,int d2,double[] k) {
        double p2=Pwl(backend,k,4,32);
        double raw1=128*q2+p2-16*d2;
        double y2=p2-16*d2;
        double p1=Pwl(raw1,k,0,128);
        double y1=p1-64*d1;
        return new double[]{512*q1+p1-64*d1+2048,y1,y2,raw1};
    }
    public sealed class Context {
        public double[] K=new double[]{1,1,1,1,1,1,1,1};
        public double[] Sums=new double[8];
        public long[] Gates=new long[8], Basis=new long[8], Both=new long[8];
        public long Clips=0,OutputClips=0;
    }
    public static void Products(Context c,int q1,int q2,double raw,int d1,int d2) {
        double[] y=Correct(q1,q2,raw,d1,d2,c.K);
        if(y[0]<0||y[0]>4095)c.OutputClips++;
        for(int bank=0;bank<2;bank++) {
            int offset=bank*4; double width=bank==0?128:32;
            double local=y[bank+1], dd=(bank==0?64*d1:16*d2);
            double magRaw=Math.Abs(bank==0?y[3]:raw);
            double threshold=0;
            for(int j=0;j<4;j++) {
                bool gate=Gate(j,local,threshold);
                bool support=magRaw>j*width;
                if(gate) { c.Sums[offset+j]+=dd*local; c.Gates[offset+j]++; }
                if(support)c.Basis[offset+j]++;
                if(gate&&support)c.Both[offset+j]++;
                threshold+=width*c.K[offset+j];
            }
        }
    }
    public static void Commit(Context c,int multiplier) {
        int[] num={1,3,6,12};
        for(int j=0;j<8;j++) {
            double step=num[j%4]/(j<4?262144000.0:16384000.0);
            double request=c.K[j]-step*multiplier*c.Sums[j];
            if(request<0||request>2)c.Clips++;
            c.K[j]=Math.Min(Math.Max(request,0),2);
            c.Sums[j]=0;
        }
    }
    public sealed class RunResult {
        public string[] StateFiles;
        public string ProbeFile;
        public long[] GateCountsContinuous, GateCountsQuantized, BasisContinuous,BasisQuantized,BothContinuous,BothQuantized;
        public double[] FinalContinuous,FinalQuantized;
        public long ContinuousCoefficientClips,QuantizedCoefficientClips,ContinuousOutputClips,QuantizedOutputClips;
        public long PhysicalOverloads,GeneratedSamples;
        public int Windows,Selected,ProbeWindows;
    }
    public static void Grid(string path,int points,double a1,double b1,double a2,double b2) {
        var xs=new List<double>();
        for(int i=0;i<points;i++)xs.Add(-0.82+(i+0.5)*(1.64/points));
        for(int i=0;i<8;i++) {
            double t=-0.875+i*0.25;
            xs.Add(Math.BitDecrement(t));xs.Add(t);xs.Add(Math.BitIncrement(t));
        }
        using(var stream=new BinaryWriter(File.Open(path,FileMode.CreateNew)))
            foreach(double x in xs)foreach(int d1 in new int[]{-1,1})foreach(int d2 in new int[]{-1,1}) {
                stream.Write(x);stream.Write((double)d1);stream.Write((double)d2);
                foreach(double v in Plant(x,d1,d2,a1,b1,a2,b2))stream.Write(v);
            }
    }
    public static void Edges(string path) {
        using(var stream=new BinaryWriter(File.Open(path,FileMode.CreateNew)))
        foreach(double width in new double[]{32,128})
        foreach(double[] slopes in new double[][]{new double[]{1,1,1,1},new double[]{0.9,1.2,0.8,1.1}})
        for(int j=-4;j<=3;j++)foreach(double raw in new double[]{Math.BitDecrement(j*width),j*width,Math.BitIncrement(j*width)}) {
            if(raw< -4*width||raw>=4*width)continue;
            double p=Pwl(raw,slopes,0,width);
            stream.Write(width);stream.Write(raw);foreach(double k in slopes)stream.Write(k);stream.Write(p);
        }
    }
    public static void GateEdges(string path) {
        using(var stream=new BinaryWriter(File.Open(path,FileMode.CreateNew)))
        foreach(double width in new double[]{32,128})
        foreach(double[] k in new double[][]{new double[]{1,1,1,1},new double[]{0.9,1.2,0.8,1.1}}) {
            double t=0;
            for(int j=0;j<4;j++) {
                foreach(double local in new double[]{Math.BitDecrement(t),t,Math.BitIncrement(t),
                                                    Math.BitDecrement(-t),-t,Math.BitIncrement(-t)}) {
                    stream.Write(width);foreach(double v in k)stream.Write(v);stream.Write((double)j);
                    stream.Write(local);stream.Write(Gate(j,local,t)?1.0:0.0);
                }
                t+=width*k[j];
            }
        }
    }
    public static void SarEdges(string path) {
        using(var stream=new BinaryWriter(File.Open(path,FileMode.CreateNew)))
        for(int i=0;i<=256;i++) {
            double t=-1+i/128.0;
            foreach(double v in new double[]{Math.BitDecrement(t),t,Math.BitIncrement(t)}) {
                stream.Write(v);stream.Write(Quantize(v));stream.Write(v< -1?1.0:0.0);stream.Write(v>=1?1.0:0.0);
            }
        }
    }
    public static RunResult Run(string folder,string name,ulong seed,double a1,double b1,double a2,double b2,
                                int windows,int selected,int multiplier,int[] probeWindows) {
        Directory.CreateDirectory(folder);
        string stem=Path.Combine(folder,name+"_"+seed);
        string[] stateFiles={stem+"_continuous.bin",stem+"_sar8.bin"};
        string probeFile=stem+"_probes.bin";
        var c=new Context[]{new Context(),new Context()};
        var probes=new HashSet<int>(probeWindows);
        long overload=0;int probeCount=0;
        using(var s0=new BinaryWriter(File.Open(stateFiles[0],FileMode.CreateNew)))
        using(var s1=new BinaryWriter(File.Open(stateFiles[1],FileMode.CreateNew)))
        using(var audit=new BinaryWriter(File.Open(probeFile,FileMode.CreateNew))) {
            var streams=new BinaryWriter[]{s0,s1};
            for(int mode=0;mode<2;mode++)foreach(double k in c[mode].K)streams[mode].Write(k);
            for(int w=0;w<windows;w++) {
                bool save=probes.Contains(w);
                if(save) {
                    audit.Write((double)w);
                    for(int mode=0;mode<2;mode++)foreach(double k in c[mode].K)audit.Write(k);
                    probeCount++;
                }
                for(int n=0;n<selected;n++) {
                    long index=120L*w+n;
                    double x=Input(seed,index); int d1=Tag(seed,2,index),d2=Tag(seed,3,index);
                    double[] raw=Plant(x,d1,d2,a1,b1,a2,b2);
                    if(x< -1||x>=1||raw[2]< -1||raw[2]>=1||raw[3]< -1||raw[3]>=1)overload++;
                    Products(c[0],(int)raw[0],(int)raw[1],raw[4],d1,d2);
                    Products(c[1],(int)raw[0],(int)raw[1],raw[5],d1,d2);
                    if(save) { audit.Write(x);audit.Write((double)d1);audit.Write((double)d2);foreach(double v in raw)audit.Write(v); }
                }
                if(save)for(int mode=0;mode<2;mode++)foreach(double p in c[mode].Sums)audit.Write(p);
                for(int mode=0;mode<2;mode++) {
                    Commit(c[mode],multiplier);
                    foreach(double k in c[mode].K)streams[mode].Write(k);
                }
                if(save)for(int mode=0;mode<2;mode++)foreach(double k in c[mode].K)audit.Write(k);
            }
        }
        return new RunResult {StateFiles=stateFiles,ProbeFile=probeFile,
            GateCountsContinuous=c[0].Gates,GateCountsQuantized=c[1].Gates,
            BasisContinuous=c[0].Basis,BasisQuantized=c[1].Basis,BothContinuous=c[0].Both,BothQuantized=c[1].Both,
            FinalContinuous=c[0].K,FinalQuantized=c[1].K,
            ContinuousCoefficientClips=c[0].Clips,QuantizedCoefficientClips=c[1].Clips,
            ContinuousOutputClips=c[0].OutputClips,QuantizedOutputClips=c[1].OutputClips,
            PhysicalOverloads=overload,GeneratedSamples=(long)windows*selected,
            Windows=windows,Selected=selected,ProbeWindows=probeCount};
    }
}
