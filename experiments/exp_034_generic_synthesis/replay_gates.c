/* Settled, zero-delay replay of the five generic combinational cells and
 * two synchronous FF cells retained by EXP-034. It is not a timing simulator.
 * Unknown bits remain unknown; no X-to-zero coercion is permitted.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint32_t op, y, a, b, s; } Gate;
typedef struct { uint32_t q, d, r, e, reset_value; } FlipFlop;
static uint8_t and3(uint8_t a, uint8_t b) {
    return a == 0 || b == 0 ? 0 : a == 1 && b == 1 ? 1 : 2;
}
static uint8_t or3(uint8_t a, uint8_t b) {
    return a == 1 || b == 1 ? 1 : a == 0 && b == 0 ? 0 : 2;
}
static uint8_t xor3(uint8_t a, uint8_t b) {
    return a < 2 && b < 2 ? a ^ b : 2;
}
static uint8_t mux3(uint8_t a, uint8_t b, uint8_t s) {
    return s == 0 ? a : s == 1 ? b : a == b ? a : 2;
}
static void fail(const char *message) { fprintf(stderr, "%s\n", message); exit(1); }
static void read_exact(void *target, size_t width, size_t count, FILE *file) {
    if (fread(target, width, count, file) != count) fail("Truncated replay input");
}
static void evaluate(uint8_t *values, const Gate *gates, uint32_t count) {
    for (uint32_t i = 0; i < count; ++i) {
        const Gate *g = &gates[i];
        uint8_t a = values[g->a], b = values[g->b];
        switch (g->op) {
        case 0: values[g->y] = and3(a, b); break;
        case 1: values[g->y] = or3(a, b); break;
        case 2: values[g->y] = xor3(a, b); break;
        case 3: values[g->y] = a < 2 ? 1 - a : 2; break;
        case 4: values[g->y] = mux3(a, b, values[g->s]); break;
        default: fail("Unsupported opcode");
        }
    }
}
static void rising_edge(uint8_t *values, const FlipFlop *ffs, uint32_t count,
                        uint8_t *next) {
    for (uint32_t i = 0; i < count; ++i) {
        const FlipFlop *f = &ffs[i];
        uint8_t r = values[f->r], e = values[f->e];
        if (r > 1 || (r == 0 && e > 1)) fail("Unknown FF control");
        next[i] = r == 1 ? f->reset_value : e == 1 ? values[f->d] : values[f->q];
    }
    for (uint32_t i = 0; i < count; ++i) values[ffs[i].q] = next[i];
}
static void check_outputs(const uint8_t *values, const uint32_t *outputs,
                          const uint8_t *expected, uint32_t count,
                          uint32_t pass, uint32_t row) {
    for (uint32_t bit = 0; bit < count; ++bit)
        if (values[outputs[bit]] != expected[bit]) {
            fprintf(stderr, "Mismatch pass=%u row=%u output_bit=%u actual=%u expected=%u\n",
                    pass, row, bit, values[outputs[bit]], expected[bit]);
            exit(1);
        }
}
static void selftest(void) {
    /* Known-bit truth tables plus the cases where a known value controls X. */
    for (uint8_t a = 0; a < 2; ++a)
        for (uint8_t b = 0; b < 2; ++b) {
            if (and3(a,b) != (a & b) || or3(a,b) != (a | b) ||
                xor3(a,b) != (a ^ b) || mux3(a,b,0) != a || mux3(a,b,1) != b)
                fail("Primitive truth-table self-test failed");
        }
    if (and3(0,2) != 0 || and3(1,2) != 2 || or3(1,2) != 1 ||
        or3(0,2) != 2 || xor3(0,2) != 2 || mux3(1,1,2) != 1 || mux3(0,1,2) != 2)
        fail("Unknown-state self-test failed");
    /* Reset priority, enabled capture, idle hold, and simultaneous state. */
    uint8_t v[] = {0,1,2,1,0,1,0,1}, next[2];
    FlipFlop f[] = {{3,4,1,0,0}, {4,3,0,1,1}};
    rising_edge(v,f,2,next);
    if (v[3] != 0 || v[4] != 1) fail("Reset/capture self-test failed");
    f[0].r = 0; f[0].e = 0; f[1].e = 0;
    rising_edge(v,f,2,next);
    if (v[3] != 0 || v[4] != 1) fail("Idle-hold self-test failed");
    f[0].e = 1; f[1].e = 1;
    rising_edge(v,f,2,next);
    if (v[3] != 1 || v[4] != 0) fail("Simultaneous-capture self-test failed");
}
int main(int argc, char **argv) {
    selftest();
    if (argc != 3) fail("Usage: replay_gates netlist.bin vectors.bin");
    FILE *net = fopen(argv[1], "rb"), *records = fopen(argv[2], "rb");
    if (!net || !records) fail("Cannot open input file");
    uint32_t h[10];
    read_exact(h,4,10,net);
    if (h[0] != 0xADC03401 || h[5] != 13) fail("Unsupported netlist format");
    uint32_t nv=h[1], ng=h[2], nf=h[3], ni=h[4], no=h[5];
    uint32_t valid=h[6], reset=h[7], online=h[9];
    Gate *gates=calloc(ng,sizeof(Gate));
    FlipFlop *ffs=calloc(nf+1,sizeof(FlipFlop));
    uint32_t *inputs=calloc(ni,4), *outputs=calloc(no,4);
    uint8_t *values=malloc(nv), *next=malloc(nf+1);
    uint8_t *row=malloc(ni+no), *zeros=calloc(no,1);
    if (!gates || !ffs || !inputs || !outputs || !values || !next || !row || !zeros)
        fail("Allocation failed");
    read_exact(gates,sizeof(Gate),ng,net); read_exact(ffs,sizeof(FlipFlop),nf,net);
    read_exact(inputs,4,ni,net); read_exact(outputs,4,no,net);
    if (fgetc(net) != EOF) fail("Unexpected netlist trailing bytes");
    fclose(net);
    uint32_t nr, checked=0, idle=0;
    read_exact(&nr,4,1,records);
    if (!nr) fail("Empty reference records");
    for (uint32_t pass=0; pass < (online ? 2u : 1u); ++pass) {
        memset(values,2,nv);
        values[0]=0; values[1]=1;
        for (uint32_t i=0; i<ni; ++i) values[inputs[i]]=0;
        if (online) {
            values[reset]=1; evaluate(values,gates,ng);
            rising_edge(values,ffs,nf,next); values[reset]=0;
        }
        if (fseek(records,4,SEEK_SET)) fail("Cannot rewind references");
        uint32_t limit=pass==0 ? nr : (nr<128 ? nr : 128);
        for (uint32_t n=0; n<limit; ++n) {
            read_exact(row,1,ni+no,records);
            if (online) {
                values[valid]=0; evaluate(values,gates,ng);
                check_outputs(values,outputs,zeros,no,pass,n);
                rising_edge(values,ffs,nf,next); ++idle;
            }
            for (uint32_t i=0; i<ni; ++i) values[inputs[i]]=row[i];
            evaluate(values,gates,ng);
            check_outputs(values,outputs,row+ni,no,pass,n);
            if (online) rising_edge(values,ffs,nf,next);
            ++checked;
        }
        if (pass==0 && fgetc(records)!=EOF) fail("Unexpected reference trailing bytes");
    }
    fclose(records);
    printf("generic gates online=%u records=%u idle_clocks=%u reset_sequences=%u passed\n",
           online,checked,idle,online ? 2 : 0);
    return 0;
}
